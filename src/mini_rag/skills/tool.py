from __future__ import annotations

from typing import Any

from mini_rag.config import get_settings
from mini_rag.skills.executor import SkillExecutor
from mini_rag.skills.registry import SkillRegistry


def run_skill_tool(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    action = str(payload.get("action") or "run").strip().lower()
    if action != "run":
        return {"ok": False, "action": action, "error": {"type": "validation_error", "message": "skill tool only supports action=run"}}

    runtime_context = payload.get("runtime_context") if isinstance(payload.get("runtime_context"), dict) else {}
    runtime_context = dict(runtime_context)
    runtime_context.setdefault("user_id", payload.get("user_id"))
    runtime_context.setdefault("role", payload.get("role"))
    runtime_context.setdefault("enterprise_db_path", str(get_settings().enterprise_db_path))
    if "permissions" not in runtime_context and isinstance(payload.get("permissions"), (dict, list)):
        runtime_context["permissions"] = payload.get("permissions")

    registry = SkillRegistry(payload.get("skills_base_dir") or "skills")
    result = SkillExecutor(registry).execute(
        {
            "skill_name": payload.get("skill_name"),
            "arguments": payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {},
            "runtime_context": runtime_context,
        }
    )
    return {
        "tool_name": "skill",
        "action": "run",
        "risk_level": "low",
        **result,
    }

