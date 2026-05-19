from __future__ import annotations

"""Trace lookup and presentation helpers.

Raw trace JSON is excellent for debugging but too verbose for API consumers. This
module converts it into a readable, stable shape for ``GET /traces/{trace_id}``.
"""

import json
from pathlib import Path
from typing import Any

from mini_rag.config import Settings


def find_trace_file(settings: Settings, trace_id: str) -> Path | None:
    """Find a saved trace by its explicit trace_id or filename suffix."""

    if not trace_id:
        return None
    trace_dir = settings.trace_dir
    if not trace_dir.exists():
        return None

    # New traces include the trace_id in the filename for O(1)-like lookup.
    direct_matches = sorted(trace_dir.glob(f"*{trace_id}*.json"), reverse=True)
    if direct_matches:
        return direct_matches[0]

    # Compatibility path for old traces whose filenames used a question hash.
    for path in sorted(trace_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("trace_id") == trace_id:
            return path
    return None


def load_trace(settings: Settings, trace_id: str) -> tuple[dict[str, Any], Path] | None:
    path = find_trace_file(settings, trace_id)
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8")), path


def extract_latest_retrieval_trace(trace: dict[str, Any]) -> dict[str, Any] | None:
    """Return the most recent retrieval trace from observations/tool events."""

    for collection_name in ("tool_events", "observations"):
        for event in reversed(trace.get(collection_name, []) or []):
            if isinstance(event, dict) and event.get("retrieval_trace"):
                return event["retrieval_trace"]
    return None


def build_readable_trace(trace: dict[str, Any], raw_trace_path: str | None = None) -> dict[str, Any]:
    """Convert raw LangGraph trace to a compact API response."""

    steps: list[dict[str, Any]] = []
    retrieval_trace = extract_latest_retrieval_trace(trace) or {}

    for item in trace.get("node_trace", []) or []:
        if not isinstance(item, dict):
            continue
        node = str(item.get("node") or "unknown")
        step = {
            "node": node,
            "latency_ms": item.get("latency_ms"),
            "status": "error" if item.get("error") else "ok",
            "input": {},
            "output": {},
        }
        if node == "build_runtime_context":
            step["input"] = {"session_id": trace.get("session_id")}
            step["output"] = {
                "standalone_query": trace.get("standalone_query"),
                "intent": trace.get("intent"),
                "entities": trace.get("entities", []),
            }
        elif node == "plan_with_llm":
            step["input"] = {"question": trace.get("question"), "role": trace.get("role")}
            step["output"] = {"execution_plan": trace.get("execution_plan", {})}
        elif node == "validate_plan":
            step["input"] = {"requested_kbs": trace.get("requested_kbs", []), "role": trace.get("role")}
            step["output"] = {"plan_validation": trace.get("plan_validation", {})}
        elif node == "react_execute":
            step["input"] = {"tasks": (trace.get("execution_plan") or {}).get("tasks", [])}
            step["output"] = {"react_status": trace.get("react_status"), "react_steps": trace.get("react_steps", [])}
        elif node == "retrieve":
            step["input"] = {"search_tasks": trace.get("search_tasks", [])}
            step["output"] = {
                "retrieval_engine": retrieval_trace.get("retrieval_engine"),
                "result_count": retrieval_trace.get("result_count"),
                "executed_queries": trace.get("executed_queries", []),
            }
        elif node == "call_tool":
            step["input"] = {"selected_tool": trace.get("selected_tool")}
            step["output"] = {"tool_calls": trace.get("tool_calls", [])}
        elif node in {"answer_with_llm", "generate_answer"}:
            step["input"] = {"source_count": len(trace.get("sources") or [])}
            step["output"] = {"answer_preview": str(trace.get("answer") or "")[:300]}
        else:
            step["output"] = {key: item.get(key) for key in ("output_keys", "error") if key in item}
        steps.append(step)

    return {
        "trace_id": trace.get("trace_id"),
        "user_id": trace.get("user_id"),
        "role": trace.get("role"),
        "session_id": trace.get("session_id"),
        "query": trace.get("question"),
        "route": trace.get("route"),
        "total_latency_ms": trace.get("total_latency_ms"),
        "used_kbs": trace.get("used_kbs", []),
        "steps": steps,
        "tool_events": trace.get("tool_events") or trace.get("observations", []),
        "mainline_log": trace.get("mainline_log", []),
        "mainline_log_text": trace.get("mainline_log_text", ""),
        "sources": trace.get("sources", []),
        "error": trace.get("error"),
        "raw_trace_path": raw_trace_path,
    }
