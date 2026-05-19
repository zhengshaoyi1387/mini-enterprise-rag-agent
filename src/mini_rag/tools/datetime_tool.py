from __future__ import annotations

from typing import Any

from mini_rag.capabilities.datetime.service import DEFAULT_TIMEZONE, build_time_context, datetime_payload_from_time_context


def get_current_datetime(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    timezone = str(payload.get("timezone") or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    ctx = build_time_context(
        timezone=timezone,
        override_now=payload.get("override_now"),
        eval_fixed_now=payload.get("eval_fixed_now"),
        settings_fixed_now=payload.get("fixed_now"),
    )
    return datetime_payload_from_time_context(ctx)
