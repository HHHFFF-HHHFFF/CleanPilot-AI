import json

from agent.tools import agent_tools


class FakeSupportRepository:
    def get_device(self, user_id):
        if user_id != "1001":
            return None
        return {
            "device_id": "D-1001",
            "model": "S9 Pro",
            "purchased_at": "2025-10-16",
            "warranty_until": "2027-10-15",
        }


def test_get_current_device_returns_structured_device_data(monkeypatch):
    monkeypatch.setattr(agent_tools, "_support_repository", FakeSupportRepository())

    result = agent_tools.get_current_device.invoke({"user_id": "1001"})

    assert json.loads(result) == {
        "device_id": "D-1001",
        "model": "S9 Pro",
        "purchased_at": "2025-10-16",
        "warranty_until": "2027-10-15",
    }


def test_get_current_device_returns_empty_when_device_is_unbound(monkeypatch):
    monkeypatch.setattr(agent_tools, "_support_repository", FakeSupportRepository())

    assert agent_tools.get_current_device.invoke({"user_id": "1002"}) == ""
