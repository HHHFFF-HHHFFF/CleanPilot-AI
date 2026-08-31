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
        "u-1,测试用户,上海,d-1,S9,2026-01-01,2028-01-01,2026-08,清扫 12 次,95%,滤网 60%,增加 2 次\n"
        "u-2,其他用户,北京,d-2,X10,2026-02-01,2028-02-01,2026-08,清扫 8 次,93%,滤网 70%,增加 1 次\n",
        encoding="utf-8",
    )
    support_repository = SupportRepository(tmp_path / "support.db")
    support_repository.seed_business_data(seed_file)
    auth_repository = AuthRepository(support_repository.database_path)
    AuthService(
        auth_repository,
        AuthSettings(jwt_secret=JWT_SECRET),
    ).set_password("u-1", "SecurePass123")
    AuthService(
        auth_repository,
        AuthSettings(jwt_secret=JWT_SECRET),
    ).set_password("u-2", "SecurePass456")
    fake_agent = FakeAgent()
    app = create_app(
        ApiSettings(jwt_secret=JWT_SECRET),
        support_repository=support_repository,
        auth_repository=auth_repository,
        agent_factory=lambda: fake_agent,
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
    assert response.json()["device"]["model"] == "S9"


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
    app, _ = build_test_app(tmp_path)
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
    assert [message["role"] for message in detail.json()["messages"]] == ["user", "assistant"]
    assert forbidden_read.status_code == 404
    assert forbidden_delete.status_code == 404
