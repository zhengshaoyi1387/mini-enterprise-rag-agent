from __future__ import annotations

from typing import Any

from mini_rag.capabilities.calendar.resolver import CALENDAR_UPDATE_FIELDS


def verify_calendar_result(payload: dict[str, Any], result: dict[str, Any]) -> None:
    if result.get("error") or str(payload.get("action") or "").lower() != "update":
        return
    event = result.get("event") if isinstance(result.get("event"), dict) else {}
    mismatches: list[dict[str, str]] = []
    for field in CALENDAR_UPDATE_FIELDS:
        if field not in payload:
            continue
        expected = str(payload.get(field) or "")
        actual = str(event.get(field) or "")
        if actual != expected:
            mismatches.append({"field": field, "expected": expected, "actual": actual})
    if mismatches:
        result["error"] = "update verification failed"
        result["mismatched_fields"] = mismatches
        result["message"] = "日程更新结果与请求不一致"
