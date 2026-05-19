from __future__ import annotations

import re
from typing import Any


def _range_value(result: dict[str, Any], key: str) -> tuple[str, str] | None:
    ranges = result.get("ranges") if isinstance(result.get("ranges"), dict) else {}
    value = ranges.get(key) if isinstance(ranges.get(key), dict) else {}
    start = str(value.get("start_date") or "").strip()
    end = str(value.get("end_date") or "").strip()
    if start and end:
        return start, end
    return None


def _contains_any(text: str, values: tuple[str, ...]) -> bool:
    text = str(text or "").lower()
    return any(value.lower() in text for value in values)


def _date_line(label: str, day: str) -> str:
    return f"{label}：{day}。"


def _range_line(label: str, value: tuple[str, str]) -> str:
    start, end = value
    if start == end:
        return _date_line(label, start)
    return f"{label}：{start} 至 {end}。"


def _requested_datetime_answer(result: dict[str, Any], context: str) -> str | None:
    context = str(context or "")
    checks = (
        ("yesterday", "昨天", ("昨天", "昨日", "yesterday")),
        ("tomorrow", "明天", ("明天", "tomorrow")),
        ("today", "今天", ("今天", "今日", "当前日期", "现在几号", "today")),
        ("last_week", "上周", ("上周", "last week")),
        ("next_week", "下周", ("下周", "next week")),
        ("this_week", "本周", ("本周", "这周", "this week")),
        ("last_month", "上月", ("上个月", "上月", "last month")),
        ("next_month", "下月", ("下个月", "下月", "next month")),
        ("this_month", "本月", ("本月", "这个月", "this month")),
    )
    for key, label, aliases in checks:
        if not _contains_any(context, aliases):
            continue
        if key == "today":
            day = str(result.get("current_date") or "").strip()
            if day:
                weekday_zh = str(result.get("weekday_zh") or "").strip()
                if "星期" in context and weekday_zh:
                    return f"当前日期：{day}，星期：{weekday_zh}。"
                return _date_line("当前日期", day)
        value = _range_value(result, key)
        if value:
            return _range_line(label, value)
    return None


def format_datetime_result(result: dict[str, Any], context: str = "") -> str:
    if result.get("error"):
        return f"工具调用失败：{result.get('error')}"
    requested = _requested_datetime_answer(result, context)
    if requested:
        return requested
    parts = [
        f"当前日期：{result.get('current_date')}",
        f"时间：{result.get('current_time')}",
    ]
    weekday_zh = str(result.get("weekday_zh") or "").strip()
    if weekday_zh:
        parts.append(f"星期：{weekday_zh}")
    timezone = str(result.get("timezone") or "").strip()
    if timezone:
        parts.append(f"时区：{timezone}")
    return re.sub(r"，+", "，", "，".join(parts)).strip("，") + "。"
