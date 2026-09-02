"""维护 Agent 与业务 Skill 的白名单映射。"""

from __future__ import annotations

from pathlib import Path

from skills.base import SkillDefinition


SKILLS_ROOT = Path(__file__).resolve().parent

FAULT_TRIAGE_SKILL = SkillDefinition(
    skill_id="fault_triage",
    display_name="故障分级诊断 Skill",
    agent_name="diagnosis_agent",
    task_modes=("fault_diagnosis",),
    instruction_path=SKILLS_ROOT / "fault_triage" / "SKILL.md",
    allowed_tools=(
        "get_current_device",
        "rag_summarize",
        "get_user_location",
        "get_weather",
    ),
)

MONTHLY_USAGE_REPORT_SKILL = SkillDefinition(
    skill_id="monthly_usage_report",
    display_name="用户月度运营报告 Skill",
    agent_name="customer_agent",
    task_modes=("usage_report",),
    instruction_path=SKILLS_ROOT / "monthly_usage_report" / "SKILL.md",
    allowed_tools=(
        "get_user_id",
        "get_current_month",
        "fetch_external_data",
        "rag_summarize",
        "get_user_location",
        "get_weather",
    ),
)

REGISTERED_SKILLS = (
    FAULT_TRIAGE_SKILL,
    MONTHLY_USAGE_REPORT_SKILL,
)


def resolve_skill(agent_name: str, task_mode: str) -> SkillDefinition | None:
    """根据受信任路由结果选择 Skill，不接受客户端直接指定。"""

    return next(
        (
            skill
            for skill in REGISTERED_SKILLS
            if skill.supports(agent_name, task_mode)
        ),
        None,
    )
