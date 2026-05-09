from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Shanghai"


def _date_range(start: datetime, end: datetime) -> dict[str, str]:
    return {"start_date": start.date().isoformat(), "end_date": end.date().isoformat()}


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    first = datetime(year, month, 1)
    return first, datetime(year, month, monthrange(year, month)[1])


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = year * 12 + (month - 1) + delta
    return month_index // 12, month_index % 12 + 1


def get_current_datetime(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    timezone = str(payload.get("timezone") or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    warning = None
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        timezone = DEFAULT_TIMEZONE
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        warning = f"invalid timezone, fallback to {DEFAULT_TIMEZONE}"

    now = datetime.now(tz)
    today_start = datetime(now.year, now.month, now.day)
    monday = today_start - timedelta(days=today_start.weekday())
    sunday = monday + timedelta(days=6)

    this_month_start, this_month_end = _month_bounds(now.year, now.month)
    last_year, last_month = _shift_month(now.year, now.month, -1)
    next_year, next_month = _shift_month(now.year, now.month, 1)
    last_month_start, last_month_end = _month_bounds(last_year, last_month)
    next_month_start, next_month_end = _month_bounds(next_year, next_month)

    result: dict[str, Any] = {
        "current_date": now.date().isoformat(),
        "current_time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "timezone": timezone,
        "ranges": {
            "today": _date_range(today_start, today_start),
            "yesterday": _date_range(today_start - timedelta(days=1), today_start - timedelta(days=1)),
            "tomorrow": _date_range(today_start + timedelta(days=1), today_start + timedelta(days=1)),
            "this_week": _date_range(monday, sunday),
            "last_week": _date_range(monday - timedelta(days=7), sunday - timedelta(days=7)),
            "next_week": _date_range(monday + timedelta(days=7), sunday + timedelta(days=7)),
            "week_after_next": _date_range(monday + timedelta(days=14), sunday + timedelta(days=14)),
            "next_next_week": _date_range(monday + timedelta(days=14), sunday + timedelta(days=14)),
            "this_month": _date_range(this_month_start, this_month_end),
            "last_month": _date_range(last_month_start, last_month_end),
            "next_month": _date_range(next_month_start, next_month_end),
            "month_after_next": _date_range(*_month_bounds(*_shift_month(now.year, now.month, 2))),
            "next_next_month": _date_range(*_month_bounds(*_shift_month(now.year, now.month, 2))),
        },
    }
    if warning:
        result["warning"] = warning
    return result
