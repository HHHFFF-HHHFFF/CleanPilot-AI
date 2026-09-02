from typing import Any

from langchain.agents import create_agent

from agent.tools.agent_tools import (
    fetch_external_data,
    get_current_month,
    get_current_device,
    get_user_id,
    get_user_location,
    get_weather,
    rag_summarize,
)
from agent.tools.middleware import log_before_model, monitor_tool, specialist_prompt_switch
from model.factory import chat_model
from utils.prompt_loader import (
    load_customer_prompts,
    load_diagnosis_prompts,
    load_knowledge_prompts,
)


class SpecialistAgent:
    name: str
    display_name: str

    def __init__(self, compiled_agent: Any):
        self.agent = compiled_agent

    def stream(self, query: str, runtime_context: dict):
        input_dict = {"messages": [{"role": "user", "content": query}]}
        return self.agent.stream(
            input_dict,
            stream_mode="values",
            context=runtime_context,
        )


class KnowledgeAgent(SpecialistAgent):
    name = "knowledge_agent"
    display_name = "知识问答 Agent"

    def __init__(self, compiled_agent: Any | None = None):
        super().__init__(
            compiled_agent
            or create_agent(
                model=chat_model,
                system_prompt=load_knowledge_prompts(),
                tools=[
                    get_current_device,
                    rag_summarize,
                    get_user_location,
                    get_weather,
                ],
                middleware=[log_before_model, monitor_tool, specialist_prompt_switch],
            )
        )


class DiagnosisAgent(SpecialistAgent):
    name = "diagnosis_agent"
    display_name = "故障诊断 Agent"

    def __init__(self, compiled_agent: Any | None = None):
        super().__init__(
            compiled_agent
            or create_agent(
                model=chat_model,
                system_prompt=load_diagnosis_prompts(),
                tools=[rag_summarize, get_user_location, get_weather],
                middleware=[log_before_model, monitor_tool, specialist_prompt_switch],
            )
        )


class CustomerAgent(SpecialistAgent):
    name = "customer_agent"
    display_name = "用户运营 Agent"

    def __init__(self, compiled_agent: Any | None = None):
        super().__init__(
            compiled_agent
            or create_agent(
                model=chat_model,
                system_prompt=load_customer_prompts(),
                tools=[
                    get_user_id,
                    get_current_month,
                    fetch_external_data,
                    rag_summarize,
                    get_user_location,
                    get_weather,
                ],
                middleware=[log_before_model, monitor_tool, specialist_prompt_switch],
            )
        )
