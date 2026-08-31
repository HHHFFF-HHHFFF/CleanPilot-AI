"""创建 FastAPI 应用并连接认证、业务仓储与多 Agent 服务。"""

from __future__ import annotations

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
    CoordinatesRequest,
    CurrentUserResponse,
    LoginRequest,
    TokenResponse,
)
from api.settings import ApiSettings
from auth.service import AuthService, AuthSettings, AuthenticationError
from auth.tokens import TokenError
from storage.auth_repository import AuthRepository
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


def create_app(
    settings: ApiSettings,
    *,
    support_repository: SupportRepository | None = None,
    auth_repository: AuthRepository | None = None,
    agent_factory: Callable[[], Any] = ReactAgent,
) -> FastAPI:
    support_repository = support_repository or SupportRepository()
    auth_repository = auth_repository or AuthRepository(support_repository.database_path)
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

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        support_repository.seed_business_data(get_abs_path(agent_config["business_seed_path"]))
        if settings.demo_password:
            for user in support_repository.list_users():
                if auth_repository.get_credential(user.user_id) is None:
                    auth_service.set_password(user.user_id, settings.demo_password)
        yield

    app = FastAPI(
        title="智扫通多 Agent 客服 API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
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

    @app.post("/api/v1/chat/stream")
    def stream_chat(
        payload: ChatRequest,
        identity: CurrentIdentity = Depends(current_identity),
    ) -> StreamingResponse:
        def generate_events() -> Iterator[str]:
            try:
                agent = agent_provider.get()
                for event in agent.execute_stream(
                    payload.query,
                    location_profile=payload.location_profile,
                    user_id=identity.user.user_id,
                ):
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception as error:
                logger.exception("流式对话处理失败：%s", error)
                yield json.dumps(
                    {"type": "error", "content": "服务暂时不可用，请稍后重试。"},
                    ensure_ascii=False,
                ) + "\n"

        return StreamingResponse(generate_events(), media_type="application/x-ndjson")

    return app
