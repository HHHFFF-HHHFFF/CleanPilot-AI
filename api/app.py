"""创建 FastAPI 应用并连接认证、业务仓储与多 Agent 服务。"""

from __future__ import annotations

import base64
import binascii
import json
import threading
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import StreamingResponse

from agent.react_agent import ReactAgent
from api.schemas import (
    ChatRequest,
    CityWeatherRequest,
    ConversationDetailResponse,
    ConversationMessageResponse,
    ConversationSummaryResponse,
    CoordinatesRequest,
    CreateConversationRequest,
    CurrentUserResponse,
    KnowledgeDocumentResponse,
    KnowledgeUploadRequest,
    LoginRequest,
    TokenResponse,
)
from api.settings import ApiSettings
from auth.service import AuthService, AuthSettings, AuthenticationError
from auth.tokens import TokenError
from storage.auth_repository import AuthRepository
from storage.conversation_repository import ConversationRepository
from storage.support_repository import SupportRepository, SupportUser
from utils.config_handler import agent_config
from utils.logger_handler import logger
from utils.location_weather import get_city_weather, get_location_weather
from utils.path_tool import get_abs_path


@dataclass(frozen=True)
class CurrentIdentity:
    user: SupportUser
    role: str


class AgentProvider:
    """延迟创建 Agent，避免健康检查和登录接口加载模型与向量库。"""

    def __init__(self, factory: Callable[[], Any]):
        self.factory = factory
        self._agent: Any | None = None
        self._lock = threading.Lock()

    def get(self) -> Any:
        if self._agent is None:
            with self._lock:
                if self._agent is None:
                    self._agent = self.factory()
        return self._agent


class KnowledgeServiceProvider:
    """延迟创建知识库服务，避免普通登录请求初始化向量模型。"""

    def __init__(self, factory: Callable[[], Any]):
        self.factory = factory
        self._service: Any | None = None
        self._lock = threading.Lock()

    def get(self) -> Any:
        if self._service is None:
            with self._lock:
                if self._service is None:
                    self._service = self.factory()
        return self._service


def create_app(
    settings: ApiSettings,
    *,
    support_repository: SupportRepository | None = None,
    auth_repository: AuthRepository | None = None,
    conversation_repository: ConversationRepository | None = None,
    agent_factory: Callable[[], Any] = ReactAgent,
    knowledge_service_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    support_repository = support_repository or SupportRepository()
    auth_repository = auth_repository or AuthRepository(support_repository.database_path)
    conversation_repository = conversation_repository or ConversationRepository(
        support_repository.database_path
    )
    auth_service = AuthService(
        auth_repository,
        AuthSettings(
            jwt_secret=settings.jwt_secret,
            token_expire_seconds=settings.token_expire_seconds,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        ),
    )
    agent_provider = AgentProvider(agent_factory)
    if knowledge_service_factory is None:
        def knowledge_service_factory():
            from rag.knowledge_service import KnowledgeBaseService
            from rag.vector_store import VectorStoreService

            return KnowledgeBaseService(VectorStoreService(), support_repository)
    knowledge_service_provider = KnowledgeServiceProvider(knowledge_service_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        support_repository.seed_business_data(get_abs_path(agent_config["business_seed_path"]))
        if settings.demo_password:
            for user in support_repository.list_users():
                if auth_repository.get_credential(user.user_id) is None:
                    auth_service.set_password(user.user_id, settings.demo_password)
        yield

    app = FastAPI(
        title="CleanPilot AI 多智能体服务 API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    bearer = HTTPBearer(auto_error=False)

    def current_identity(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> CurrentIdentity:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少访问令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            claims = auth_service.verify_token(credentials.credentials)
        except TokenError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(error),
                headers={"WWW-Authenticate": "Bearer"},
            ) from error

        credential = auth_repository.get_credential(claims.user_id)
        user = support_repository.get_user(claims.user_id)
        if credential is None or not credential.is_active or user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="当前账户不可用",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return CurrentIdentity(user=user, role=credential.role)

    def admin_identity(
        identity: CurrentIdentity = Depends(current_identity),
    ) -> CurrentIdentity:
        if identity.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="仅管理员可以访问知识库运营功能",
            )
        return identity

    def serialize_knowledge_document(document: Any) -> KnowledgeDocumentResponse:
        return KnowledgeDocumentResponse(
            document_id=document.document_id,
            filename=document.filename,
            status=document.status,
            chunk_count=document.chunk_count,
            risk_level=document.risk_level,
            failure_reason=document.failure_reason,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/auth/login", response_model=TokenResponse)
    def login(payload: LoginRequest) -> TokenResponse:
        try:
            token, expires_in = auth_service.login(payload.user_id, payload.password)
        except AuthenticationError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(error),
            ) from error
        return TokenResponse(access_token=token, expires_in=expires_in)

    @app.get("/api/v1/users/me", response_model=CurrentUserResponse)
    def get_current_user(identity: CurrentIdentity = Depends(current_identity)):
        return CurrentUserResponse(
            user_id=identity.user.user_id,
            display_name=identity.user.display_name,
            city=identity.user.city,
            role=identity.role,
            device=support_repository.get_device(identity.user.user_id),
        )

    @app.post("/api/v1/context/location-weather")
    def resolve_location_weather(
        payload: CoordinatesRequest,
        _: CurrentIdentity = Depends(current_identity),
    ) -> dict[str, Any]:
        try:
            return get_location_weather(payload.latitude, payload.longitude)
        except Exception as error:
            logger.warning("定位天气查询失败：%s", error)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="暂时无法获取当前位置天气",
            ) from error

    @app.post("/api/v1/context/city-weather")
    def resolve_city_weather(
        payload: CityWeatherRequest,
        _: CurrentIdentity = Depends(current_identity),
    ) -> dict[str, Any]:
        try:
            return get_city_weather(payload.city)
        except Exception as error:
            logger.warning("账户城市天气查询失败：%s", error)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="暂时无法获取账户城市天气",
            ) from error

    @app.get(
        "/api/v1/admin/knowledge/documents",
        response_model=list[KnowledgeDocumentResponse],
    )
    def list_knowledge_documents(
        _: CurrentIdentity = Depends(admin_identity),
    ):
        service = knowledge_service_provider.get()
        return [serialize_knowledge_document(document) for document in service.list_documents()]

    @app.post(
        "/api/v1/admin/knowledge/synchronize",
        response_model=list[KnowledgeDocumentResponse],
    )
    def synchronize_knowledge_documents(
        _: CurrentIdentity = Depends(admin_identity),
    ):
        service = knowledge_service_provider.get()
        return [
            serialize_knowledge_document(document)
            for document in service.synchronize_existing_documents()
        ]

    @app.post(
        "/api/v1/admin/knowledge/upload",
        response_model=KnowledgeDocumentResponse,
    )
    def upload_knowledge_document(
        payload: KnowledgeUploadRequest,
        _: CurrentIdentity = Depends(admin_identity),
    ):
        try:
            content = base64.b64decode(payload.content_base64, validate=True)
            document = knowledge_service_provider.get().ingest_upload(
                payload.filename,
                content,
            )
        except (binascii.Error, OSError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error) or "上传内容无效",
            ) from error
        return serialize_knowledge_document(document)

    @app.post(
        "/api/v1/admin/knowledge/documents/{document_id}/retry",
        response_model=KnowledgeDocumentResponse,
    )
    def retry_knowledge_document(
        document_id: str,
        _: CurrentIdentity = Depends(admin_identity),
    ):
        service = knowledge_service_provider.get()
        document = support_repository.get_knowledge_document(document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识文件不存在")
        try:
            return serialize_knowledge_document(service.index_file(document.source_path))
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(error),
            ) from error

    @app.delete(
        "/api/v1/admin/knowledge/documents/{document_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def remove_knowledge_document(
        document_id: str,
        _: CurrentIdentity = Depends(admin_identity),
    ) -> None:
        try:
            knowledge_service_provider.get().remove_from_index(document_id)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error

    @app.get(
        "/api/v1/conversations",
        response_model=list[ConversationSummaryResponse],
    )
    def list_conversations(
        identity: CurrentIdentity = Depends(current_identity),
    ):
        return conversation_repository.list_conversations(identity.user.user_id)

    @app.post(
        "/api/v1/conversations",
        response_model=ConversationSummaryResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_conversation(
        payload: CreateConversationRequest,
        identity: CurrentIdentity = Depends(current_identity),
    ):
        return conversation_repository.create_conversation(
            identity.user.user_id,
            payload.title,
        )

    @app.get(
        "/api/v1/conversations/{conversation_id}",
        response_model=ConversationDetailResponse,
    )
    def get_conversation(
        conversation_id: str,
        identity: CurrentIdentity = Depends(current_identity),
    ):
        result = conversation_repository.get_conversation(
            identity.user.user_id,
            conversation_id,
        )
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
        conversation, messages = result
        return ConversationDetailResponse(
            conversation=ConversationSummaryResponse(**conversation.__dict__),
            messages=[ConversationMessageResponse(**message.__dict__) for message in messages],
        )

    @app.delete(
        "/api/v1/conversations/{conversation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_conversation(
        conversation_id: str,
        identity: CurrentIdentity = Depends(current_identity),
    ) -> None:
        if not conversation_repository.delete_conversation(
            identity.user.user_id,
            conversation_id,
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    @app.post("/api/v1/chat/stream")
    def stream_chat(
        payload: ChatRequest,
        identity: CurrentIdentity = Depends(current_identity),
    ) -> StreamingResponse:
        if payload.conversation_id:
            existing_conversation = conversation_repository.get_conversation(
                identity.user.user_id,
                payload.conversation_id,
            )
            if existing_conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="会话不存在",
                )
            conversation = existing_conversation[0]
        else:
            conversation = conversation_repository.create_conversation(
                identity.user.user_id,
                payload.query,
            )
        conversation_repository.add_message(
            identity.user.user_id,
            conversation.conversation_id,
            role="user",
            content=payload.query,
        )

        def generate_events() -> Iterator[str]:
            answer_parts: list[str] = []
            traces: list[str] = []
            active_agent: str | None = None
            try:
                yield json.dumps(
                    {
                        "type": "conversation",
                        "conversation_id": conversation.conversation_id,
                        "content": conversation.title,
                    },
                    ensure_ascii=False,
                ) + "\n"
                agent = agent_provider.get()
                for event in agent.execute_stream(
                    payload.query,
                    location_profile=payload.location_profile,
                    user_id=identity.user.user_id,
                ):
                    active_agent = event.get("agent") or active_agent
                    if event.get("type") == "trace":
                        traces.append(event.get("content", ""))
                    elif event.get("type") in {"answer", "error"}:
                        answer_parts.append(event.get("content", ""))
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception as error:
                logger.exception("流式对话处理失败：%s", error)
                error_message = "服务暂时不可用，请稍后重试。"
                answer_parts.append(error_message)
                yield json.dumps(
                    {"type": "error", "content": error_message},
                    ensure_ascii=False,
                ) + "\n"
            finally:
                answer = "\n\n".join(part for part in answer_parts if part)
                if answer:
                    conversation_repository.add_message(
                        identity.user.user_id,
                        conversation.conversation_id,
                        role="assistant",
                        content=answer,
                        traces=traces,
                        agent=active_agent,
                    )

        return StreamingResponse(generate_events(), media_type="application/x-ndjson")

    return app
