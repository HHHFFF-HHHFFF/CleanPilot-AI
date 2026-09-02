from langchain_core.messages import AIMessage

from agent.contracts import RoutingDecision
from agent.react_agent import ReactAgent
from agent.router_agent import fallback_route
from agent.tools.middleware import bind_runtime_tool_arguments, ensure_skill_tool_access


class FakeRouter:
    def __init__(self, decision):
        self.decision = decision

    def route(self, query):
        return self.decision


class FakeSpecialist:
    display_name = "测试功能 Agent"

    def __init__(self):
        self.calls = []

    def stream(self, query, runtime_context):
        self.calls.append((query, runtime_context))
        yield {"messages": [AIMessage(content="测试回答")]}


def test_fallback_router_distinguishes_three_agent_domains():
    report_decision = fallback_route("请生成我的本月使用报告")
    diagnosis_decision = fallback_route("机器显示 E3 并且无法回充")
    knowledge_decision = fallback_route("扫地机器人滤网多久更换一次")

    assert report_decision.target_agent == "customer_agent"
    assert report_decision.task_mode == "usage_report"
    assert diagnosis_decision.target_agent == "diagnosis_agent"
    assert diagnosis_decision.task_mode == "fault_diagnosis"
    assert knowledge_decision.target_agent == "knowledge_agent"
    assert knowledge_decision.task_mode == "knowledge_qa"


def test_react_agent_delegates_to_selected_specialist_with_runtime_context():
    decision = RoutingDecision(
        target_agent="customer_agent",
        task_mode="usage_report",
        reason="需要查询当前用户记录。",
    )
    specialist = FakeSpecialist()
    agent = ReactAgent(
        router=FakeRouter(decision),
        specialists={"customer_agent": specialist},
    )

    events = list(
        agent.execute_stream(
            "生成本月报告",
            location_profile={"city": "上海"},
            user_id="1001",
        )
    )

    assert specialist.calls[0][1]["customer_mode"] == "usage_report"
    assert specialist.calls[0][1]["user_id"] == "1001"
    assert specialist.calls[0][1]["location_profile"] == {"city": "上海"}
    assert specialist.calls[0][1]["skill_id"] == "monthly_usage_report"
    assert "fetch_external_data" in specialist.calls[0][1]["skill_allowed_tools"]
    assert "用户月度运营报告 Skill" in events[2]["content"]
    assert events[-1] == {
        "type": "answer",
        "agent": "customer_agent",
        "content": "测试回答",
    }


def test_usage_query_is_forced_to_current_session_user():
    arguments = bind_runtime_tool_arguments(
        "fetch_external_data",
        {"user_id": "1002", "month": "2026-08"},
        {"user_id": "1001"},
    )

    assert arguments == {"user_id": "1001", "month": "2026-08"}


def test_usage_query_rejects_missing_session_user():
    try:
        bind_runtime_tool_arguments(
            "fetch_external_data",
            {"user_id": "1002", "month": "2026-08"},
            {},
        )
    except PermissionError as error:
        assert "缺少用户身份" in str(error)
    else:
        raise AssertionError("缺少会话用户时应拒绝查询个人使用记录")


def test_fault_diagnosis_loads_triage_skill():
    decision = RoutingDecision(
        target_agent="diagnosis_agent",
        task_mode="fault_diagnosis",
        reason="需要执行故障诊断。",
    )
    specialist = FakeSpecialist()
    agent = ReactAgent(
        router=FakeRouter(decision),
        specialists={"diagnosis_agent": specialist},
    )

    events = list(agent.execute_stream("设备冒烟并有焦味"))

    runtime_context = specialist.calls[0][1]
    assert runtime_context["skill_id"] == "fault_triage"
    assert runtime_context["skill_allowed_tools"] == [
        "get_current_device",
        "rag_summarize",
        "get_user_location",
        "get_weather",
    ]
    assert "故障分级诊断 Skill" in events[2]["content"]


def test_skill_tool_access_rejects_tools_outside_whitelist():
    runtime_context = {
        "skill_id": "fault_triage",
        "skill_allowed_tools": ["rag_summarize"],
    }

    ensure_skill_tool_access("rag_summarize", runtime_context)
    try:
        ensure_skill_tool_access("fetch_external_data", runtime_context)
    except PermissionError as error:
        assert "无权调用工具" in str(error)
    else:
        raise AssertionError("Skill 调用白名单外工具时应被拒绝")


def test_device_query_is_forced_to_current_session_user():
    arguments = bind_runtime_tool_arguments(
        "get_current_device",
        {"user_id": "1002"},
        {"user_id": "1001"},
    )

    assert arguments == {"user_id": "1001"}
