import base64
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.app import create_app
from api.settings import ApiSettings
from auth.service import AuthService, AuthSettings
from storage.auth_repository import AuthRepository
from storage.support_repository import SupportRepository


JWT_SECRET = "test-secret-that-is-longer-than-thirty-two-characters"


class FakeAgent:
    def __init__(self):
        self.calls = []

    def execute_stream(
        self,
        query,
        location_profile=None,
        user_id=None,
        conversation_history=None,
        memory_context="",
        classified_memories=None,
    ):
        self.calls.append(
            {
                "query": query,
                "location_profile": location_profile,
                "user_id": user_id,
                "conversation_history": conversation_history or [],
                "memory_context": memory_context,
                "classified_memories": classified_memories or [],
            }
        )
        yield {"type": "trace", "agent": "router_agent", "content": "已完成路由。"}
        if "故障" in query:
            yield {
                "type": "trace",
                "agent": "diagnosis_agent",
                "content": "已启用故障诊断 Skill。",
                "task_mode": "fault_diagnosis",
                "skill_id": "fault_triage",
            }
        yield {"type": "answer", "agent": "knowledge_agent", "content": "测试回答"}


class FakeKnowledgeService:
    def __init__(self, source_path):
        self.document = SimpleNamespace(
            document_id="doc-1",
            source_path=str(source_path),
            filename="manual.txt",
            status="indexed",
            chunk_count=3,
            risk_level="none",
            failure_reason=None,
            created_at="2026-08-31T10:00:00+00:00",
            updated_at="2026-08-31T10:00:00+00:00",
        )
        self.uploaded = None
        self.removed = None

    def list_documents(self):
        return [self.document]

    def synchronize_existing_documents(self):
        return [self.document]

    def ingest_upload(self, filename, content):
        self.uploaded = (filename, content)
        return self.document

    def index_file(self, source_path):
        return self.document

    def remove_from_index(self, document_id):
        self.removed = document_id


def build_test_app(tmp_path):
    seed_file = tmp_path / "records.csv"
    seed_file.write_text(
        "user_id,display_name,city,device_id,device_model,purchased_at,warranty_until,month,feature,efficiency,consumables,comparison\n"
        "u-1,测试用户,上海,d-1,S9,2026-01-01,2028-01-01,2026-08,清扫 12 次,95%,滤网 60%,增加 2 次\n"
        "u-2,其他用户,北京,d-2,X10,2026-02-01,2028-02-01,2026-08,清扫 8 次,93%,滤网 70%,增加 1 次\n",
        encoding="utf-8",
    )
    support_repository = SupportRepository(tmp_path / "support.db")
    support_repository.seed_business_data(seed_file)
    knowledge_file = tmp_path / "manual.txt"
    knowledge_file.write_text("测试知识", encoding="utf-8")
    support_repository.save_knowledge_document(
        document_id="doc-1",
        source_path=knowledge_file,
        filename=knowledge_file.name,
        content_hash="test-hash",
        status="indexed",
        chunk_count=3,
    )
    auth_repository = AuthRepository(support_repository.database_path)
    AuthService(
        auth_repository,
        AuthSettings(jwt_secret=JWT_SECRET),
    ).set_password("u-1", "SecurePass123", role="admin")
    AuthService(
        auth_repository,
        AuthSettings(jwt_secret=JWT_SECRET),
    ).set_password("u-2", "SecurePass456")
    fake_agent = FakeAgent()
    fake_knowledge_service = FakeKnowledgeService(knowledge_file)
    app = create_app(
        ApiSettings(jwt_secret=JWT_SECRET),
        support_repository=support_repository,
        auth_repository=auth_repository,
        agent_factory=lambda: fake_agent,
        knowledge_service_factory=lambda: fake_knowledge_service,
    )
    return app, fake_agent


def login(client: TestClient, user_id="u-1", password="SecurePass123") -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"user_id": user_id, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_login_and_current_user_endpoint(tmp_path):
    app, _ = build_test_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/v1/users/me").status_code == 401
        assert client.post(
            "/api/v1/auth/login",
            json={"user_id": "u-1", "password": "WrongPass123"},
        ).status_code == 401

        token = login(client)
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["user_id"] == "u-1"
    assert response.json()["role"] == "admin"
    assert response.json()["device"]["model"] == "S9"


def test_knowledge_admin_endpoints_enforce_role_and_manage_documents(tmp_path):
    app, _ = build_test_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/knowledge/documents").status_code == 401

        customer_token = login(client, "u-2", "SecurePass456")
        customer_response = client.get(
            "/api/v1/admin/knowledge/documents",
            headers={"Authorization": f"Bearer {customer_token}"},
        )

        admin_token = login(client)
        headers = {"Authorization": f"Bearer {admin_token}"}
        listed = client.get("/api/v1/admin/knowledge/documents", headers=headers)
        synchronized = client.post("/api/v1/admin/knowledge/synchronize", headers=headers)
        uploaded = client.post(
            "/api/v1/admin/knowledge/upload",
            headers=headers,
            json={
                "filename": "manual.txt",
                "content_base64": base64.b64encode("测试知识".encode()).decode(),
            },
        )
        retried = client.post(
            "/api/v1/admin/knowledge/documents/doc-1/retry",
            headers=headers,
        )
        removed = client.delete(
            "/api/v1/admin/knowledge/documents/doc-1",
            headers=headers,
        )

    assert customer_response.status_code == 403
    assert listed.status_code == 200
    assert listed.json()[0]["filename"] == "manual.txt"
    assert synchronized.status_code == 200
    assert uploaded.status_code == 200
    assert retried.status_code == 200
    assert removed.status_code == 204


def test_local_react_origin_is_allowed_by_cors(tmp_path):
    app, _ = build_test_app(tmp_path)
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"

    with TestClient(app) as client:
        delete_preflight = client.options(
            "/api/v1/conversations/example",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert delete_preflight.status_code == 200
    assert "DELETE" in delete_preflight.headers["access-control-allow-methods"]


def test_chat_stream_uses_token_user_and_rejects_forged_identity(tmp_path):
    app, fake_agent = build_test_app(tmp_path)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}

        rejected = client.post(
            "/api/v1/chat/stream",
            headers=headers,
            json={"query": "生成报告", "user_id": "u-2"},
        )
        response = client.post(
            "/api/v1/chat/stream",
            headers=headers,
            json={
                "query": "生成报告",
                "location_profile": {"city": "上海", "temperature": 26},
            },
        )

    assert rejected.status_code == 422
    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200
    assert events[-1]["content"] == "测试回答"
    assert fake_agent.calls == [
        {
            "query": "生成报告",
            "location_profile": {"city": "上海", "temperature": 26},
            "user_id": "u-1",
            "conversation_history": [],
            "memory_context": "",
            "classified_memories": [],
        }
    ]


def test_location_weather_requires_login_and_validates_coordinates(tmp_path, monkeypatch):
    app, _ = build_test_app(tmp_path)
    monkeypatch.setattr(
        "api.app.get_location_weather",
        lambda latitude, longitude: {
            "city": "上海",
            "latitude": latitude,
            "longitude": longitude,
            "condition": "晴",
            "temperature": 26,
            "apparent_temperature": 27,
            "humidity": 52,
            "wind_speed": 8,
            "observed_at": "2026-08-31T10:00",
        },
    )
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/context/location-weather",
            json={"latitude": 31.2, "longitude": 121.5},
        ).status_code == 401
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        invalid = client.post(
            "/api/v1/context/location-weather",
            headers=headers,
            json={"latitude": 100, "longitude": 121.5},
        )
        response = client.post(
            "/api/v1/context/location-weather",
            headers=headers,
            json={"latitude": 31.2, "longitude": 121.5},
        )

    assert invalid.status_code == 422
    assert response.status_code == 200
    assert response.json()["city"] == "上海"


def test_city_weather_fallback_uses_authenticated_endpoint(tmp_path, monkeypatch):
    app, _ = build_test_app(tmp_path)
    monkeypatch.setattr(
        "api.app.get_city_weather",
        lambda city: {"city": city, "condition": "晴", "temperature": 26},
    )
    with TestClient(app) as client:
        token = login(client)
        response = client.post(
            "/api/v1/context/city-weather",
            headers={"Authorization": f"Bearer {token}"},
            json={"city": "上海"},
        )

    assert response.status_code == 200
    assert response.json()["city"] == "上海"


def test_conversation_history_is_persisted_and_isolated(tmp_path):
    app, fake_agent = build_test_app(tmp_path)
    with TestClient(app) as client:
        user_one_token = login(client)
        user_one_headers = {"Authorization": f"Bearer {user_one_token}"}
        created = client.post(
            "/api/v1/conversations",
            headers=user_one_headers,
            json={"title": "主刷维护建议"},
        )
        conversation_id = created.json()["conversation_id"]
        streamed = client.post(
            "/api/v1/chat/stream",
            headers=user_one_headers,
            json={"query": "主刷怎么维护？", "conversation_id": conversation_id},
        )
        detail = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=user_one_headers,
        )
        second_stream = client.post(
            "/api/v1/chat/stream",
            headers=user_one_headers,
            json={"query": "那边刷呢？", "conversation_id": conversation_id},
        )

        user_two_token = login(client, "u-2", "SecurePass456")
        user_two_headers = {"Authorization": f"Bearer {user_two_token}"}
        forbidden_read = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=user_two_headers,
        )
        forbidden_delete = client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers=user_two_headers,
        )

    assert created.status_code == 201
    assert streamed.status_code == 200
    assert second_stream.status_code == 200
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "assistant"]
    assert fake_agent.calls[1]["conversation_history"] == [
        {"role": "user", "content": "主刷怎么维护？"},
        {"role": "assistant", "content": "测试回答"},
    ]
    assert forbidden_read.status_code == 404
    assert forbidden_delete.status_code == 404


def test_fault_conversation_is_reused_as_account_memory(tmp_path):
    app, fake_agent = build_test_app(tmp_path)
    with TestClient(app) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}
        first = client.post(
            "/api/v1/chat/stream",
            headers=headers,
            json={"query": "设备出现故障 E3"},
        )
        conversation_id = json.loads(first.text.splitlines()[0])["conversation_id"]
        second = client.post(
            "/api/v1/chat/stream",
            headers=headers,
            json={"query": "继续排查", "conversation_id": conversation_id},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    recalled_content = "\n".join(
        memory["content"] for memory in fake_agent.calls[1]["classified_memories"]
    )
    assert "设备出现故障 E3" in recalled_content
    assert "测试回答" in recalled_content


def test_user_can_manage_only_their_own_profile_memories(tmp_path):
    app, _ = build_test_app(tmp_path)
    with TestClient(app) as client:
        user_one_token = login(client)
        user_one_headers = {"Authorization": f"Bearer {user_one_token}"}
        client.post(
            "/api/v1/chat/stream",
            headers=user_one_headers,
            json={"query": "我家有猫，大约 80 平方米，我对噪音比较敏感"},
        )
        listed = client.get("/api/v1/memories", headers=user_one_headers)
        memory = next(
            item for item in listed.json() if item["memory_key"] == "household_pet"
        )

        user_two_token = login(client, "u-2", "SecurePass456")
        user_two_headers = {"Authorization": f"Bearer {user_two_token}"}
        forbidden = client.patch(
            f"/api/v1/memories/{memory['memory_id']}",
            headers=user_two_headers,
            json={"content": "越权修改"},
        )
        updated = client.patch(
            f"/api/v1/memories/{memory['memory_id']}",
            headers=user_one_headers,
            json={"content": "家庭环境中有两只猫"},
        )
        removed = client.delete(
            f"/api/v1/memories/{memory['memory_id']}",
            headers=user_one_headers,
        )
        listed_after_delete = client.get("/api/v1/memories", headers=user_one_headers)

    assert listed.status_code == 200
    assert len([item for item in listed.json() if item["memory_type"] == "profile"]) == 3
    assert forbidden.status_code == 404
    assert updated.json()["content"] == "家庭环境中有两只猫"
    assert updated.json()["version"] == 2
    assert removed.status_code == 204
    assert memory["memory_id"] not in {
        item["memory_id"] for item in listed_after_delete.json()
    }
