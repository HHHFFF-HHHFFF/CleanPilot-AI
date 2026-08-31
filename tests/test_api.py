import json

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

    def execute_stream(self, query, location_profile=None, user_id=None):
        self.calls.append(
            {
                "query": query,
                "location_profile": location_profile,
                "user_id": user_id,
            }
        )
        yield {"type": "trace", "agent": "router_agent", "content": "已完成路由。"}
        yield {"type": "answer", "agent": "knowledge_agent", "content": "测试回答"}


def build_test_app(tmp_path):
    seed_file = tmp_path / "records.csv"
    seed_file.write_text(
        "user_id,display_name,city,device_id,device_model,purchased_at,warranty_until,month,feature,efficiency,consumables,comparison\n"
        "u-1,测试用户,上海,d-1,S9,2026-01-01,2028-01-01,2026-08,清扫 12 次,95%,滤网 60%,增加 2 次\n",
        encoding="utf-8",
    )
    support_repository = SupportRepository(tmp_path / "support.db")
    support_repository.seed_business_data(seed_file)
    auth_repository = AuthRepository(support_repository.database_path)
    AuthService(
        auth_repository,
        AuthSettings(jwt_secret=JWT_SECRET),
    ).set_password("u-1", "SecurePass123")
    fake_agent = FakeAgent()
    app = create_app(
        ApiSettings(jwt_secret=JWT_SECRET),
        support_repository=support_repository,
        auth_repository=auth_repository,
        agent_factory=lambda: fake_agent,
    )
    return app, fake_agent


def login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"user_id": "u-1", "password": "SecurePass123"},
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
    assert response.json()["device"]["model"] == "S9"


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
        }
    ]
