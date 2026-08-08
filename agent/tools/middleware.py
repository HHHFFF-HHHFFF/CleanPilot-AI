from typing import Callable

from langchain.agents import AgentState
from langchain.agents.middleware import ModelRequest, before_model, dynamic_prompt, wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from utils.logger_handler import logger
from utils.prompt_loader import load_report_prompts, load_system_prompts


@wrap_tool_call
def monitor_tool(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    tool_name = request.tool_call["name"]
    logger.info(f"[tool monitor] 执行工具: {tool_name}")
    logger.info(f"[tool monitor] 传入参数: {request.tool_call['args']}")

    try:
        location_profile = request.runtime.context.get("location_profile", {})
        if tool_name == "get_user_location" and location_profile:
            city = location_profile.get("city", "当前位置")
            return ToolMessage(
                content=f"用户当前城市：{city}",
                tool_call_id=request.tool_call["id"],
            )

        result = handler(request)
        logger.info(f"[tool monitor] 工具 {tool_name} 调用成功")

        if tool_name == "fill_context_for_report":
            request.runtime.context["report"] = True

        return result
    except Exception as error:
        logger.error(f"工具 {tool_name} 调用失败，原因：{error}")
        raise


@before_model
def log_before_model(state: AgentState, runtime: Runtime):
    logger.info(f"[log_before_model] 即将调用模型，包含 {len(state['messages'])} 条消息")
    logger.debug(
        f"[log_before_model] {type(state['messages'][-1]).__name__} | "
        f"{state['messages'][-1].content.strip()}"
    )
    return None


@dynamic_prompt
def report_prompt_switch(request: ModelRequest):
    if request.runtime.context.get("report", False):
        return load_report_prompts()
    return load_system_prompts()