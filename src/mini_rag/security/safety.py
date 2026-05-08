from __future__ import annotations

"""Lightweight request safety helpers.

This is not a replacement for a production safety classifier. It is a strict,
auditable baseline for an interview project: high-risk secret exfiltration and
system-prompt extraction attempts should be blocked before they reach tools.
"""

from typing import Final

DANGEROUS_KEYWORDS: Final[tuple[str, ...]] = (
    "api key",
    "apikey",
    "secret",
    "system prompt",
    "系统提示词",
    "密钥",
    "泄露",
    "密码",
    "token",
    "删除所有文件",
    "读取环境变量",
)


def looks_dangerous(text: str | None) -> bool:
    value = (text or "").lower()
    return any(keyword.lower() in value for keyword in DANGEROUS_KEYWORDS)
