from __future__ import annotations

import os
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mini_rag.capabilities.datetime.formatter import format_datetime_result
from mini_rag.core.contracts import DateRange, TimeContext

DEFAULT_TIMEZONE = "Asia/Shanghai"
WEEKDAYS_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
EVAL_FIXED_NOW_ENV = "AGENT_EVAL_FIXED_NOW"


def _safe_timezone(timezone: str | None) -> tuple[str, ZoneInfo]:
    name = str(timezone or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        return name, ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return DEFAULT_TIMEZONE, ZoneInfo(DEFAULT_TIMEZONE)


def _split_fixed_now(value: str, default_timezone: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return "", default_timezone
    parts = text.rsplit(" ", 1)
    if len(parts) == 2 and "/" in parts[1]:
        return parts[0], parts[1]
    return text, default_timezone


def _parse_now(value: str | datetime | None, timezone: str) -> datetime | None:
    if value is None or value == "":
        return None
    timezone, tz = _safe_timezone(timezone)
    if isinstance(value, datetime):
        parsed = value
    else:
        text, embedded_timezone = _split_fixed_now(str(value), timezone)
        if embedded_timezone != timezone:
            timezone, tz = _safe_timezone(embedded_timezone)
        normalized = text.replace("Z", "+00:00").replace(" ", "T", 1)
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            parsed = datetime.strptime(text, "%Y-%m-%d")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = year * 12 + (month - 1) + delta
    return month_index // 12, month_index % 12 + 1


def _range(start: datetime, end: datetime) -> DateRange:
    return DateRange(start_date=start.date().isoformat(), end_date=end.date().isoformat())


def _month_range(year: int, month: int) -> DateRange:
    start, end = _month_bounds(year, month)
    return DateRange(start_date=start, end_date=end)


def build_time_context(
    *,
    timezone: str = DEFAULT_TIMEZONE,
    override_now: str | datetime | None = None,
    eval_fixed_now: str | datetime | None = None,
    settings_fixed_now: str | datetime | None = None,
) -> TimeContext:
    """Build the deterministic request-level time context.

    Precedence follows the architecture contract:
    request override > eval env/config > settings fixed now > real clock.
    """

    fixed_value = override_now
    if fixed_value in (None, ""):
        fixed_value = eval_fixed_now if eval_fixed_now not in (None, "") else os.getenv(EVAL_FIXED_NOW_ENV)
    if fixed_value in (None, ""):
        fixed_value = settings_fixed_now

    timezone, tz = _safe_timezone(timezone)
    now = _parse_now(fixed_value, timezone) if fixed_value not in (None, "") else datetime.now(tz)
    timezone = getattr(now.tzinfo, "key", timezone) or timezone
    today_start = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
    monday = today_start - timedelta(days=today_start.weekday())
    sunday = monday + timedelta(days=6)
    last_year, last_month = _shift_month(now.year, now.month, -1)
    next_year, next_month = _shift_month(now.year, now.month, 1)

    return TimeContext(
        timezone=timezone,
        now=now,
        today=today_start.date().isoformat(),
        yesterday=(today_start - timedelta(days=1)).date().isoformat(),
        tomorrow=(today_start + timedelta(days=1)).date().isoformat(),
        day_after_tomorrow=(today_start + timedelta(days=2)).date().isoformat(),
        this_week=_range(monday, sunday),
        last_week=_range(monday - timedelta(days=7), sunday - timedelta(days=7)),
        next_week=_range(monday + timedelta(days=7), sunday + timedelta(days=7)),
        this_month=_month_range(now.year, now.month),
        last_month=_month_range(last_year, last_month),
        next_month=_month_range(next_year, next_month),
    )


def datetime_payload_from_time_context(ctx: TimeContext) -> dict[str, Any]:
    now = ctx.now
    if now is None:
        ctx = build_time_context(timezone=ctx.timezone)
        now = ctx.now
    assert now is not None
    today_start = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
    monday = today_start - timedelta(days=today_start.weekday())
    sunday = monday + timedelta(days=6)
    month_after_next = _month_range(*_shift_month(now.year, now.month, 2))
    next_next_week = _range(monday + timedelta(days=14), sunday + timedelta(days=14))
    ranges = {
        "today": DateRange(ctx.today, ctx.today).to_dict(),
        "yesterday": DateRange(ctx.yesterday, ctx.yesterday).to_dict(),
        "tomorrow": DateRange(ctx.tomorrow, ctx.tomorrow).to_dict(),
        "day_after_tomorrow": DateRange(ctx.day_after_tomorrow, ctx.day_after_tomorrow).to_dict(),
        "this_week": ctx.this_week.to_dict(),
        "last_week": ctx.last_week.to_dict(),
        "next_week": ctx.next_week.to_dict(),
        "next_next_week": next_next_week.to_dict(),
        "this_month": ctx.this_month.to_dict(),
        "last_month": ctx.last_month.to_dict(),
        "next_month": ctx.next_month.to_dict(),
        "month_after_next": month_after_next.to_dict(),
        "next_next_month": month_after_next.to_dict(),
    }
    return {
        "current_date": ctx.today,
        "current_time": now.strftime("%H:%M:%S"),
        "weekday": now.strftime("%A"),
        "weekday_zh": WEEKDAYS_ZH[now.weekday()],
        "timezone": ctx.timezone,
        "ranges": ranges,
    }


def default_datetime_payload(timezone: str = "Asia/Shanghai") -> dict[str, Any]:
    return {"timezone": timezone}


def build_datetime_tool_context(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "domain": "datetime",
        "tool_name": "get_current_datetime",
        "tool_input": dict(payload),
        "result_summary": format_datetime_result(result, context=str(payload.get("query") or "")),
        "trace_id": None,
    }
