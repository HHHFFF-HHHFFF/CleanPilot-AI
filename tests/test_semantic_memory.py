from memory.semantic_memory import ProfileOutput, SemanticMemoryService, SummaryOutput


class FakeModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return self.outputs.pop(0)


def test_semantic_summary_merges_previous_summary_and_new_messages():
    service = SemanticMemoryService(
        FakeModel([SummaryOutput(summary="用户养猫，设备曾出现 E3，尚未解决。"), ProfileOutput()])
    )

    summary = service.summarize(
        "用户养猫。",
        [{"role": "user", "content": "设备出现 E3"}],
    )

    assert "养猫" in summary
    assert "E3" in summary


def test_profile_model_rejects_sensitive_or_inferred_candidates():
    service = SemanticMemoryService(
        FakeModel(
            [
                SummaryOutput(summary=""),
                ProfileOutput.model_validate(
                    {
                        "facts": [
                            {
                                "key": "household_pet",
                                "content": "家庭环境中有猫",
                                "confidence": 0.96,
                                "explicit": True,
                                "sensitive": False,
                            },
                            {
                                "key": "home_area",
                                "content": "精确地址中的住宅面积",
                                "confidence": 0.99,
                                "explicit": True,
                                "sensitive": True,
                            },
                        ]
                    }
                ),
            ]
        )
    )

    facts = service.extract_profile_facts("我家有猫，并包含一段敏感地址")

    assert [(fact.key, fact.content) for fact in facts] == [
        ("household_pet", "家庭环境中有猫")
    ]
