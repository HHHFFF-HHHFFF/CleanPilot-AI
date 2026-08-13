"""Lightweight prompt-injection checks for uploaded knowledge documents."""

from __future__ import annotations

from dataclasses import dataclass


SUSPICIOUS_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "system prompt",
    "developer message",
    "reveal your instructions",
    "忽略之前的指令",
    "忽略上述指令",
    "系统提示词",
    "开发者消息",
    "泄露提示词",
)


@dataclass(frozen=True)
class InjectionScanResult:
    risk_level: str
    matched_patterns: tuple[str, ...]

    @property
    def is_blocked(self) -> bool:
        return self.risk_level == "high"


def scan_text_for_prompt_injection(text: str) -> InjectionScanResult:
    """Flag instruction-like text embedded in untrusted knowledge documents."""
    normalized_text = text.casefold()
    matches = tuple(pattern for pattern in SUSPICIOUS_PATTERNS if pattern.casefold() in normalized_text)
    return InjectionScanResult(risk_level="high" if matches else "none", matched_patterns=matches)
