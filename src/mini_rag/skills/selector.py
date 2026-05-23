from __future__ import annotations

from typing import Any

from mini_rag.skills.registry import SkillRegistry


def find_candidate_skills(
    query: str,
    *,
    intent_tags: list[str] | None = None,
    registry: SkillRegistry | None = None,
) -> list[dict[str, Any]]:
    """Thin selector wrapper for callers that do not need a registry object."""

    return (registry or SkillRegistry()).find_candidate_skills(query, intent_tags=intent_tags)

