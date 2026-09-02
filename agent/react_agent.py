from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from agent.router_agent import RouterAgent
from agent.specialist_agents import CustomerAgent, DiagnosisAgent, KnowledgeAgent
from skills.registry import resolve_skill


TOOL_DISPLAY_NAMES = {
    "rag_summarize": "检索知识库",
    "get_weather": "查询实时天气",
    "get_user_location": "获取当前城市",
    "get_user_id": "获取用户信息",
    "get_current_month": "获取当前日期",
    "get_current_device": "查询当前设备",
    "fetch_external_data": "查询使用记录",
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
        "decision": "需要确认当前会话用户，才能查询个性化使用记录。",
        "running": "正在获取当前会话用户标识。",
        "completed": "已获得当前会话用户标识，准备查询对应记录。",
    },
    "get_current_month": {
        "decision": "需要确认时间范围，才能定位对应的使用记录。",
        "running": "正在获取当前时间范围。",
        "completed": "已获得时间范围，准备匹配对应记录。",
    },
    "get_current_device": {
        "decision": "需要确认当前用户绑定的设备型号，才能匹配对应故障资料和排查流程。",
        "running": "正在查询当前账户绑定的设备信息。",
        "completed": "已获得设备型号与保修信息，正在匹配对应诊断流程。",
    },
    "fetch_external_data": {
        "decision": "需要查询当前用户的使用记录，为个性化建议提供依据。",
        "running": "正在查询当前用户的历史使用记录。",
        "completed": "已获得使用记录，正在结合知识库形成建议。",
    },
}


class ReactAgent:
    def __init__(
        self,
        router: Any | None = None,
        specialists: dict[str, Any] | None = None,
    ):
        self.router = router or RouterAgent()
        self.specialists = specialists or {
            "knowledge_agent": KnowledgeAgent(),
            "diagnosis_agent": DiagnosisAgent(),
            "customer_agent": CustomerAgent(),
        }

    def execute_stream(
        self,
        query: str,
        location_profile: dict | None = None,
        user_id: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        memory_context: str = "",
        classified_memories: list[dict[str, str]] | None = None,
    ):
        yield {
            "type": "trace",
            "agent": "router_agent",
            "content": "调度 Agent 正在识别问题类型与所需权限。",
        }

        decision = self.router.route(query)
        specialist = self.specialists[decision.target_agent]
        skill = resolve_skill(decision.target_agent, decision.task_mode)
        yield {
            "type": "trace",
            "agent": "router_agent",
            "content": f"{decision.reason} 已交由{specialist.display_name}处理。",
        }
        if skill is not None:
            yield {
                "type": "trace",
                "agent": decision.target_agent,
                "content": f"已启用{skill.display_name}，将按照标准业务流程执行。",
                "task_mode": decision.task_mode,
                "skill_id": skill.skill_id,
            }

        runtime_context = {
            "agent_name": decision.target_agent,
            "task_mode": decision.task_mode,
            "customer_mode": decision.task_mode,
            "location_profile": location_profile or {},
            "user_id": user_id or "",
            "skill_id": skill.skill_id if skill else "",
            "skill_name": skill.display_name if skill else "",
            "skill_instruction": skill.instruction if skill else "",
            "skill_allowed_tools": list(skill.allowed_tools) if skill else [],
        }
        scoped_memory = []
        for memory in classified_memories or []:
            memory_agent = memory.get("agent_name", "")
            memory_skill = memory.get("skill_id", "")
            if memory_agent and memory_agent != decision.target_agent:
                continue
            if memory_skill and (skill is None or memory_skill != skill.skill_id):
                continue
            content = memory.get("content", "").strip()
            if content:
                scoped_memory.append(content)
        scoped_memory_context = memory_context
        if scoped_memory:
            scoped_section = "相关长期记忆：\n" + "\n\n".join(scoped_memory)
            scoped_memory_context = "\n\n".join(
                section for section in [memory_context, scoped_section] if section
            )

        for chunk in specialist.stream(
            query,
            runtime_context,
            conversation_history=conversation_history,
            memory_context=scoped_memory_context,
        ):
            latest_message = chunk["messages"][-1]
            content = (
                latest_message.content.strip()
                if isinstance(latest_message.content, str)
                else ""
            )

            if isinstance(latest_message, ToolMessage):
                tool_name = TOOL_DISPLAY_NAMES.get(latest_message.name, "工具")
                process_note = TOOL_PROCESS_NOTES.get(latest_message.name, {})
                if getattr(latest_message, "status", "success") == "error":
                    yield {
                        "type": "trace",
                        "agent": decision.target_agent,
                        "content": f"{tool_name}暂时不可用，正在使用其他可用信息继续处理。",
                    }
                else:
                    yield {
                        "type": "trace",
                        "agent": decision.target_agent,
                        "content": f"完成：{process_note.get('completed', f'已完成{tool_name}。')}",
                    }
            elif isinstance(latest_message, AIMessage) and latest_message.tool_calls:
                for tool_call in latest_message.tool_calls:
                    tool_key = tool_call["name"]
                    tool_name = TOOL_DISPLAY_NAMES.get(tool_key, tool_key)
                    process_note = TOOL_PROCESS_NOTES.get(tool_key, {})
                    yield {
                        "type": "trace",
                        "agent": decision.target_agent,
                        "content": f"决策：{process_note.get('decision', f'需要调用{tool_name}获取补充信息。')}",
                    }
                    yield {
                        "type": "trace",
                        "agent": decision.target_agent,
                        "content": f"执行：{process_note.get('running', f'正在调用{tool_name}。')}",
                    }
            elif isinstance(latest_message, AIMessage) and content:
                yield {
                    "type": "trace",
                    "agent": decision.target_agent,
                    "content": f"{specialist.display_name}已完成信息核验与整合。",
                }
                yield {
                    "type": "answer",
                    "agent": decision.target_agent,
                    "content": content,
                }


if __name__ == "__main__":
    agent = ReactAgent()
    for event in agent.execute_stream("独居老人适合用哪种型号的扫地机器人？"):
        print(f"[{event['type']}] {event['content']}")
