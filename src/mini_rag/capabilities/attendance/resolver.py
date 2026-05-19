from __future__ import annotations

import re
from typing import Any

ATTENDANCE_STATUSES = frozenset({"present", "late", "leave", "absent"})


def canonical_status_filter_set(payload: dict[str, Any]) -> set[str]:
    """Normalize attendance status filters from structured task payloads."""

    values: list[str] = []
    for raw in (payload.get("status_filters"), payload.get("status_filter")):
        if raw in (None, "", [], {}):
            continue
        if isinstance(raw, (list, tuple, set)):
            values.extend(str(item).strip() for item in raw)
        else:
            values.extend(part.strip() for part in re.split(r"[,|，、/]+", str(raw)))
    return {value for value in values if value in ATTENDANCE_STATUSES}


def normalize_attendance_status_fields(payload: dict[str, Any]) -> None:
    normalized = [status for status in ("present", "late", "leave", "absent") if status in canonical_status_filter_set(payload)]
    if len(normalized) > 1:
        payload["status_filters"] = normalized
        payload.pop("status_filter", None)
    elif len(normalized) == 1:
        payload["status_filter"] = normalized[0]
        payload.pop("status_filters", None)
