from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mini_rag.config import get_settings
from mini_rag.skills.registry import SkillRegistry
from mini_rag.skills.schemas import validate_json_schema
from mini_rag.skills.trace import skill_trace_event


class SkillExecutor:
    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.registry = registry or SkillRegistry()

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        skill_name = str(request.get("skill_name") or "").strip()
        events: list[dict[str, Any]] = []
        manifest = self.registry.get_skill(skill_name)
        if manifest is None:
            error = {"type": "validation_error", "message": f"unknown skill: {skill_name}"}
            return self._failure(skill_name, error, events, started, validated_input=False)
        events.append(skill_trace_event(skill_name, "selected", reason="skill manifest found"))

        arguments = request.get("arguments") if isinstance(request.get("arguments"), dict) else {}
        input_errors = validate_json_schema(manifest.input_schema, arguments)
        if input_errors:
            error = {"type": "validation_error", "message": "; ".join(input_errors)}
            events.append(skill_trace_event(skill_name, "input_validated", ok=False, error=error))
            return self._failure(skill_name, error, events, started, validated_input=False)
        events.append(skill_trace_event(skill_name, "input_validated", reason="input schema ok"))

        runtime_context = request.get("runtime_context") if isinstance(request.get("runtime_context"), dict) else {}
        runtime_context = _normalize_runtime_context_paths(runtime_context)
        permission_tokens = permission_tokens_from_runtime_context(runtime_context)
        missing = [token for token in manifest.required_permissions if token not in permission_tokens]
        if missing:
            error = {
                "type": "permission_denied",
                "message": f"missing skill permissions: {', '.join(missing)}",
                "missing_permissions": missing,
            }
            events.append(skill_trace_event(skill_name, "permission_checked", ok=False, error=error))
            return self._failure(skill_name, error, events, started, validated_input=True)
        events.append(skill_trace_event(skill_name, "permission_checked", reason="required permissions satisfied"))

        instruction_path = manifest.instruction_path
        if instruction_path.exists():
            events.append(skill_trace_event(skill_name, "loaded", reason="SKILL.md available"))
        else:
            events.append(skill_trace_event(skill_name, "loaded", ok=False, reason="SKILL.md missing"))

        if manifest.risk_level != "read_only":
            error = {"type": "permission_denied", "message": "current runtime only allows read_only skills"}
            events.append(skill_trace_event(skill_name, "failed", ok=False, error=error))
            return self._failure(skill_name, error, events, started, validated_input=True)

        if not manifest.entrypoint_path.exists():
            error = {"type": "execution_error", "message": f"entrypoint not found: {manifest.entrypoint}"}
            events.append(skill_trace_event(skill_name, "failed", ok=False, error=error))
            return self._failure(skill_name, error, events, started, validated_input=True)

        payload = {"arguments": arguments, "runtime_context": runtime_context, "skill_name": skill_name}
        exec_started = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, str(manifest.entrypoint_path.name)],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                cwd=str(manifest.skill_dir),
                timeout=manifest.timeout_seconds,
                env=_safe_subprocess_env(),
                check=False,
            )
        except subprocess.TimeoutExpired:
            error = {"type": "timeout", "message": f"skill timed out after {manifest.timeout_seconds}s"}
            events.append(skill_trace_event(skill_name, "failed", ok=False, latency_ms=_elapsed_ms(exec_started), error=error))
            return self._failure(skill_name, error, events, started, validated_input=True)

        exec_latency = _elapsed_ms(exec_started)
        if completed.returncode != 0:
            error = {
                "type": "execution_error",
                "message": (completed.stderr or completed.stdout or f"process exited {completed.returncode}")[:1000],
            }
            events.append(skill_trace_event(skill_name, "executed", ok=False, latency_ms=exec_latency, error=error))
            return self._failure(skill_name, error, events, started, validated_input=True)

        try:
            result = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            error = {"type": "execution_error", "message": f"skill stdout is not JSON: {exc}"}
            events.append(skill_trace_event(skill_name, "executed", ok=False, latency_ms=exec_latency, error=error))
            return self._failure(skill_name, error, events, started, validated_input=True)
        events.append(skill_trace_event(skill_name, "executed", latency_ms=exec_latency, reason="process completed"))

        output_errors = validate_json_schema(manifest.output_schema, result)
        if output_errors:
            error = {"type": "output_schema_error", "message": "; ".join(output_errors)}
            events.append(skill_trace_event(skill_name, "output_validated", ok=False, error=error))
            return self._failure(skill_name, error, events, started, validated_input=True, result=result)
        events.append(skill_trace_event(skill_name, "output_validated", reason="output schema ok"))

        latency = _elapsed_ms(started)
        return {
            "ok": True,
            "skill_name": skill_name,
            "result": result,
            "error": None,
            "trace": {
                "validated_input": True,
                "validated_output": True,
                "latency_ms": latency,
                "entrypoint": manifest.entrypoint,
                "events": events,
            },
        }

    def _failure(
        self,
        skill_name: str,
        error: dict[str, Any],
        events: list[dict[str, Any]],
        started: float,
        *,
        validated_input: bool,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "skill_name": skill_name,
            "result": result,
            "error": error,
            "trace": {
                "validated_input": bool(validated_input),
                "validated_output": False,
                "latency_ms": _elapsed_ms(started),
                "events": events,
            },
        }


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def _safe_subprocess_env() -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[3]
    src_path = repo_root / "src"
    enterprise_db_path = _resolve_path_for_subprocess(get_settings().enterprise_db_path)
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(src_path),
        "PYTHONIOENCODING": "utf-8",
        "MINI_RAG_ENTERPRISE_DB_PATH": str(enterprise_db_path),
    }


def _normalize_runtime_context_paths(runtime_context: dict[str, Any]) -> dict[str, Any]:
    output = dict(runtime_context)
    for key in ("enterprise_db_path", "db_path"):
        value = output.get(key)
        if value:
            output[key] = str(_resolve_path_for_subprocess(value))
    return output


def _resolve_path_for_subprocess(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def permission_tokens_from_runtime_context(runtime_context: dict[str, Any]) -> set[str]:
    permissions = runtime_context.get("permissions")
    tokens: set[str] = set()
    if isinstance(permissions, list):
        tokens.update(str(item).strip() for item in permissions if str(item).strip())
    elif isinstance(permissions, dict):
        for key, value in permissions.items():
            if isinstance(value, bool) and value:
                tokens.add(str(key))
        tool_actions = permissions.get("tool_actions")
        if isinstance(tool_actions, dict):
            for tool_name, actions in tool_actions.items():
                action_set = {str(action) for action in (actions or [])}
                for action in action_set:
                    tokens.add(f"{tool_name}.{action}")
                if str(tool_name) == "query_attendance_summary" and action_set:
                    tokens.add("attendance:read")
                if str(tool_name) == "search_knowledge_base" and action_set:
                    tokens.add("rag:read")
                if str(tool_name) == "manage_company_calendar":
                    if "query" in action_set or "*" in action_set:
                        tokens.add("calendar:read")
                    if {"create", "update", "delete"} & action_set:
                        tokens.add("calendar:write")
    if runtime_context.get("role") == "admin":
        tokens.update({"attendance:read", "rag:read", "calendar:read"})
    return {token for token in tokens if token}


def _permission_tokens(runtime_context: dict[str, Any]) -> set[str]:
    return permission_tokens_from_runtime_context(runtime_context)
