"""从用户明确表达中提取低敏感度画像事实。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileFact:
    key: str
    content: str
    confidence: float = 0.9


def extract_profile_facts(text: str) -> list[ProfileFact]:
    """仅提取明确陈述，不推断位置、健康、支付等敏感信息。"""
    normalized = " ".join(text.split())
    facts: dict[str, ProfileFact] = {}

    area_match = None
    if "我家" in normalized or "家里" in normalized:
        area_match = re.search(
            r"(?:面积(?:是|约为)?|大约|大概|约)?\s*(\d{2,3})\s*(?:平|平方米)",
            normalized,
        )
    if area_match:
        facts["home_area"] = ProfileFact(
            key="home_area",
            content=f"居住面积约 {area_match.group(1)} 平方米",
            confidence=0.95,
        )

    pet_match = re.search(r"(?:我家|家里)(?:有|养了?|养着)\s*(猫|狗|宠物)", normalized)
    if pet_match:
        facts["household_pet"] = ProfileFact(
            key="household_pet",
            content=f"家庭环境中有{pet_match.group(1)}",
            confidence=0.95,
        )

    member_match = re.search(r"(?:我家|家里)(?:有|住着)\s*(老人|小孩|儿童)", normalized)
    if member_match:
        facts["household_member"] = ProfileFact(
            key="household_member",
            content=f"家庭成员中有{member_match.group(1)}",
            confidence=0.9,
        )

    if re.search(r"(?:我|家里人)(?:对)?噪音(?:比较|很)?敏感", normalized):
        facts["noise_preference"] = ProfileFact(
            key="noise_preference",
            content="偏好低噪音清洁方案",
            confidence=0.95,
        )

    preference_match = re.search(
        r"我(?:更)?(?:喜欢|偏好|希望)(?:使用)?([^，。！？]{2,30})",
        normalized,
    )
    if preference_match:
        preference = preference_match.group(1).strip()
        facts["cleaning_preference"] = ProfileFact(
            key="cleaning_preference",
            content=f"清洁偏好：{preference}",
            confidence=0.85,
        )

    return list(facts.values())
