from memory.profile_extractor import extract_profile_facts


def test_extract_profile_facts_only_from_explicit_supported_statements():
    facts = {
        fact.key: fact
        for fact in extract_profile_facts(
            "我家大约 80 平方米，家里有猫，我对噪音比较敏感"
        )
    }

    assert facts["home_area"].content == "居住面积约 80 平方米"
    assert facts["household_pet"].content == "家庭环境中有猫"
    assert facts["noise_preference"].content == "偏好低噪音清洁方案"
    assert extract_profile_facts("帮我推荐一个扫地机器人") == []
