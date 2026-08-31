from typing import Literal

from pydantic import BaseModel, Field


AgentName = Literal["knowledge_agent", "diagnosis_agent", "customer_agent"]
TaskMode = Literal[
    "knowledge_qa",
    "fault_diagnosis",
    "customer_service",
    "usage_report",
    "warranty_query",
    "maintenance_advice",
]


class RoutingDecision(BaseModel):
    target_agent: AgentName
    task_mode: TaskMode
    reason: str = Field(description="面向用户展示的简短路由说明，不包含隐藏推理过程")
