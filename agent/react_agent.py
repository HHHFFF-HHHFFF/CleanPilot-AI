from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from agent.tools.agent_tools import (
    fetch_external_data,
    fill_context_for_report,
    get_current_month,
    get_user_id,
    get_user_location,
    get_weather,
    rag_summarize,
)
from agent.tools.middleware import log_before_model, monitor_tool, report_prompt_switch
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts

TOOL_DISPLAY_NAMES = {
    "rag_summarize": "检索知识库",
    "get_weather": "查询实时天气",
    "get_user_location": "获取当前城市",
    "get_user_id": "获取用户信息",
    "get_current_month": "获取当前日期",
    "fetch_external_data": "查询使用记录",
    "fill_context_for_report": "准备报告上下文",
}

TOOL_PROCESS_NOTES = {
    "rag_summarize": {
        "decision": "需要核对知识库中的产品规格、使用建议或售后规则。",
        "running": "正在检索与问题相关的知识库资料。",
        "completed": "已获得知识库参考信息，正在提炼可执行建议。",
    },
    "get_weather": {
        "decision": "需要结合当前天气判断清洁场景、耗材或设备使用建议。",
        "running": "正在查询目标城市的实时天气。",
        "completed": "已获得天气信息，正在评估其对使用建议的影响。",
    },
    "get_user_location": {
        "decision": "需要确认当前城市，才能提供本地化天气建议。",
        "running": "正在读取用户已授权的当前城市。",
        "completed": "已获得当前城市信息，后续可据此补充天气建议。",
    },
    "get_user_id": {
        "decision": "需要确认用户标识，才能查询个性化使用记录。",
        "running": "正在获取用户标识。",
        "completed": "已获得用户标识，准备查询历史使用记录。",
    },
    "get_current_month": {
        "decision": "需要确认当前时间范围，才能定位对应的历史记录。",
        "running": "正在获取当前时间范围。",
        "completed": "已获得时间范围，准备匹配对应记录。",
    },
    "fetch_external_data": {
        "decision": "需要查询外部使用记录，为建议提供个性化依据。",
        "running": "正在查询用户历史使用记录。",
        "completed": "已获得使用记录，正在结合知识库形成建议。",
    },
    "fill_context_for_report": {
        "decision": "当前任务需要切换到结构化报告处理模式。",
        "running": "正在准备报告所需的上下文信息。",
        "completed": "报告上下文已准备完成，正在组织结构化结论。",
    },
}


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[
                rag_summarize,
                get_weather,
                get_user_id,
                get_user_location,
                get_current_month,
                fetch_external_data,
                fill_context_for_report,
            ],
            middleware=[log_before_model, monitor_tool, report_prompt_switch],
        )

    def execute_stream(
        self,
        query: str,
        location_profile: dict | None = None,
        user_id: str | None = None,
    ):
        input_dict = {"messages": [{"role": "user", "content": query}]}
        runtime_context = {
            "report": False,
            "location_profile": location_profile or {},
            "user_id": user_id or "",
        }
        yield {
            "type": "trace",
            "content": "已理解问题，正在分析需要使用的知识、环境与用户信息。",
        }

        for chunk in self.agent.stream(input_dict, stream_mode="values", context=runtime_context):
            latest_message = chunk["messages"][-1]
            content = latest_message.content.strip() if isinstance(latest_message.content, str) else ""

            if isinstance(latest_message, ToolMessage):
                tool_name = TOOL_DISPLAY_NAMES.get(latest_message.name, "工具")
                process_note = TOOL_PROCESS_NOTES.get(latest_message.name, {})
                if getattr(latest_message, "status", "success") == "error":
                    yield {
                        "type": "trace",
                        "content": f"{tool_name}暂时不可用，正在调整可用信息后继续处理。",
                    }
                else:
                    yield {
                        "type": "trace",
                        "content": f"完成：{process_note.get('completed', f'已完成{tool_name}。')}",
                    }
            elif isinstance(latest_message, AIMessage) and latest_message.tool_calls:
                for tool_call in latest_message.tool_calls:
                    tool_key = tool_call["name"]
                    tool_name = TOOL_DISPLAY_NAMES.get(tool_key, tool_key)
                    process_note = TOOL_PROCESS_NOTES.get(tool_key, {})
                    yield {
                        "type": "trace",
                        "content": f"决策：{process_note.get('decision', f'需要调用{tool_name}获取补充信息。')}",
                    }
                    yield {
                        "type": "trace",
                        "content": f"执行：{process_note.get('running', f'正在调用{tool_name}。')}",
                    }
            elif isinstance(latest_message, AIMessage) and content:
                yield {
                    "type": "trace",
                    "content": "已完成信息核验与整合，正在生成最终建议。",
                }
                yield {"type": "answer", "content": content}


if __name__ == "__main__":
    agent = ReactAgent()
    for event in agent.execute_stream("独居老人适合用哪种型号的扫地机器人？"):
        print(f"[{event['type']}] {event['content']}")
