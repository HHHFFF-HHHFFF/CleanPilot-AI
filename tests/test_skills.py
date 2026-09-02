from skills.registry import resolve_skill


def test_skill_registry_maps_only_supported_agent_and_task_mode():
    diagnosis_skill = resolve_skill("diagnosis_agent", "fault_diagnosis")
    report_skill = resolve_skill("customer_agent", "usage_report")

    assert diagnosis_skill is not None
    assert diagnosis_skill.skill_id == "fault_triage"
    assert report_skill is not None
    assert report_skill.skill_id == "monthly_usage_report"
    assert resolve_skill("customer_agent", "fault_diagnosis") is None
    assert resolve_skill("diagnosis_agent", "usage_report") is None
    assert resolve_skill("knowledge_agent", "knowledge_qa") is None


def test_skill_instructions_define_workflow_and_security_boundary():
    diagnosis_skill = resolve_skill("diagnosis_agent", "fault_diagnosis")
    report_skill = resolve_skill("customer_agent", "usage_report")

    assert diagnosis_skill is not None
    assert "安全优先" in diagnosis_skill.instruction
    assert "get_current_device" in diagnosis_skill.instruction
    assert "禁止指导拆机维修" in diagnosis_skill.instruction
    assert report_skill is not None
    assert "fetch_external_data" in report_skill.instruction
    assert "禁止查询或披露其他用户记录" in report_skill.instruction
