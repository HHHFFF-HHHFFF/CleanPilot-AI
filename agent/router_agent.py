import json
import re
from typing import Any

from langchain.agents import create_agent

from agent.contracts import RoutingDecision
from model.factory import chat_model
from utils.logger_handler import logger
from utils.prompt_loader import load_router_prompts


class RouterAgent:
    def __init__(self, compiled_agent: Any | None = None):
        self.agent = compiled_agent or create_agent(
            model=chat_model,
            tools=[],
            system_prompt=load_router_prompts(),
            response_format=RoutingDecision,
        )

    def route(self, query: str) -> RoutingDecision:
        try:
            result = self.agent.invoke(
                {"messages": [{"role": "user", "content": query}]}
            )
            structured_response = result.get("structured_response")
            if structured_response is not None:
                return RoutingDecision.model_validate(structured_response)

            messages = result.get("messages", [])
            if messages:
                return self._parse_text_response(messages[-1].content)
        except Exception as error:
            logger.warning("[router agent] 模型路由失败，使用本地兜底规则：%s", error)

        return fallback_route(query)

    @staticmethod
    def _parse_text_response(content: Any) -> RoutingDecision:
        if not isinstance(content, str):
            raise ValueError("调度 Agent 未返回可解析的文本")
        matched_json = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if matched_json is None:
            raise ValueError("调度 Agent 返回结果中缺少 JSON 对象")
        return RoutingDecision.model_validate(json.loads(matched_json.group(0)))


def fallback_route(query: str) -> RoutingDecision:
    normalized_query = query.casefold()

    report_keywords = ("报告", "使用记录", "使用情况", "月报", "数据统计")
    customer_keywords = ("我的设备", "我的机器", "保修", "购买日期", "耗材剩余")
    diagnosis_keywords = (
        "故障",
        "报错",
        "报警",
        "错误码",
        "无法启动",
        "不能启动",
        "不回充",
        "回充失败",
        "异响",
        "漏水",
        "不出水",
        "卡住",
        "e1",
        "e2",
        "e3",
        "e4",
    )

    if any(keyword in normalized_query for keyword in report_keywords):
        return RoutingDecision(
            target_agent="customer_agent",
            task_mode="usage_report",
            reason="该问题需要结合当前用户的设备使用记录生成报告。",
        )

    if "保修" in normalized_query:
        return RoutingDecision(
            target_agent="customer_agent",
            task_mode="warranty_query",
            reason="该问题需要查询当前用户的设备与保修信息。",
        )

    if any(keyword in normalized_query for keyword in diagnosis_keywords):
        return RoutingDecision(
            target_agent="diagnosis_agent",
            task_mode="fault_diagnosis",
            reason="该问题包含故障现象，需要执行安全的设备诊断流程。",
        )

    if any(keyword in normalized_query for keyword in customer_keywords):
        return RoutingDecision(
            target_agent="customer_agent",
            task_mode="customer_service",
            reason="该问题需要结合当前用户的设备或使用数据回答。",
        )

    return RoutingDecision(
        target_agent="knowledge_agent",
        task_mode="knowledge_qa",
        reason="该问题属于通用产品知识或使用建议。",
    )
