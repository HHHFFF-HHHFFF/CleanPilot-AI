from typing import Callable

from langchain.agents import AgentState
from langchain.agents.middleware import ModelRequest, before_model, dynamic_prompt, wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.types import Command

from utils.logger_handler import logger
from utils.prompt_loader import load_customer_prompts, load_report_prompts


def bind_runtime_tool_arguments(
    tool_name: str,
    arguments: dict,
    runtime_context: dict,
) -> dict:
    bound_arguments = dict(arguments)
    if tool_name != "fetch_external_data":
        return bound_arguments

    user_id = runtime_context.get("user_id", "")
    if not user_id:
        raise PermissionError("当前会话缺少用户身份，不能查询个人使用记录。")
    bound_arguments["user_id"] = user_id
    return bound_arguments


@wrap_tool_call
def monitor_tool(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    tool_name = request.tool_call["name"]
    agent_name = request.runtime.context.get("agent_name", "unknown_agent")
    logger.info(f"[tool monitor] Agent={agent_name} 执行工具: {tool_name}")
    logger.info(f"[tool monitor] 传入参数: {request.tool_call['args']}")

    try:
        location_profile = request.runtime.context.get("location_profile", {})
        if tool_name == "get_user_location" and location_profile:
            city = location_profile.get("city", "当前位置")
            return ToolMessage(
                content=f"用户当前城市：{city}",
                tool_call_id=request.tool_call["id"],
            )

        user_id = request.runtime.context.get("user_id", "")
        if tool_name == "get_user_id" and user_id:
            return ToolMessage(
                content=f"当前会话用户 ID：{user_id}",
                tool_call_id=request.tool_call["id"],
            )

        if tool_name == "fetch_external_data":
            try:
                request.tool_call["args"] = bind_runtime_tool_arguments(
                    tool_name,
                    request.tool_call.get("args", {}),
                    request.runtime.context,
                )
            except PermissionError as error:
                return ToolMessage(
                    content=str(error),
                    tool_call_id=request.tool_call["id"],
                    status="error",
                )

        result = handler(request)
        logger.info(f"[tool monitor] 工具 {tool_name} 调用成功")

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
def customer_prompt_switch(request: ModelRequest):
    if request.runtime.context.get("customer_mode") == "usage_report":
        return load_report_prompts()
    return load_customer_prompts()
