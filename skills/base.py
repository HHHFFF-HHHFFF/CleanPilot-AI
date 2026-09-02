"""定义业务 Skill 的统一数据协议。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path


@dataclass(frozen=True)
class SkillDefinition:
    """描述一个可被指定 Agent 执行的受控业务流程。"""

    skill_id: str
    display_name: str
    agent_name: str
    task_modes: tuple[str, ...]
    instruction_path: Path
    allowed_tools: tuple[str, ...]

    @cached_property
    def instruction(self) -> str:
        return self.instruction_path.read_text(encoding="utf-8").strip()

    def supports(self, agent_name: str, task_mode: str) -> bool:
        return self.agent_name == agent_name and task_mode in self.task_modes
