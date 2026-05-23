from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ZH_DATE_RE = re.compile(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日")
WEEKDAYS_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
WEEKDAY_ALIASES = (
    (0, ("周一", "星期一", "礼拜一", "monday")),
    (1, ("周二", "星期二", "礼拜二", "tuesday")),
    (2, ("周三", "星期三", "礼拜三", "wednesday")),
    (3, ("周四", "星期四", "礼拜四", "thursday")),
    (4, ("周五", "星期五", "礼拜五", "friday")),
    (5, ("周六", "星期六", "礼拜六", "saturday")),
    (6, ("周日", "周天", "星期日", "星期天", "礼拜日", "礼拜天", "sunday")),
)


def _weekday_zh(day: str) -> str:
    try:
        return WEEKDAYS_ZH[date.fromisoformat(day).weekday()]
    except Exception:
        return ""


def _resolved_item(label: str, start_date: str, end_date: str | None = None) -> dict[str, str]:
    end = end_date or start_date
    return {
        "label": label,
        "start_date": start_date,
        "end_date": end,
        "weekday_zh": _weekday_zh(start_date) if start_date == end else "",
    }


def _empty_resolved_time() -> dict[str, Any]:
    return {"kind": "none", "items": []}


def _dedupe_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (str(item.get("label") or ""), str(item.get("start_date") or ""), str(item.get("end_date") or ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = year * 12 + (month - 1) + delta
    return month_index // 12, month_index % 12 + 1


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{monthrange(year, month)[1]:02d}"


def _context_today(ctx: Any) -> date:
    value = str(getattr(ctx, "today", "") or "").strip()
    if not value and isinstance(ctx, dict):
        value = str(ctx.get("today") or ctx.get("current_date") or "").strip()
    if not value:
        raise ValueError("time_context missing today/current_date")
    return date.fromisoformat(value)


def _context_current_minutes(ctx: Any) -> int | None:
    now = getattr(ctx, "now", None)
    if isinstance(now, datetime):
        return now.hour * 60 + now.minute
    value = ""
    if isinstance(ctx, dict):
        value = str(ctx.get("current_time") or "").strip()
    if not value:
        return None
    match = re.match(r"^(\d{1,2}):(\d{2})", value)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def _range_from_context(ctx: Any, key: str) -> tuple[str, str] | None:
    if isinstance(ctx, dict):
        ranges = ctx.get("ranges") if isinstance(ctx.get("ranges"), dict) else {}
        value = ranges.get(key) if isinstance(ranges.get(key), dict) else {}
        start = str(value.get("start_date") or "").strip()
        end = str(value.get("end_date") or "").strip()
        return (start, end) if DATE_RE.fullmatch(start) and DATE_RE.fullmatch(end) else None
    value = getattr(ctx, key, None)
    start = str(getattr(value, "start_date", "") or "").strip()
    end = str(getattr(value, "end_date", "") or "").strip()
    return (start, end) if DATE_RE.fullmatch(start) and DATE_RE.fullmatch(end) else None


def _week_range(ctx: Any, key: str) -> tuple[str, str] | None:
    if key == "next_next_week":
        base = _range_from_context(ctx, "next_week")
        if not base:
            return None
        start = (date.fromisoformat(base[0]) + timedelta(days=7)).isoformat()
        end = (date.fromisoformat(base[1]) + timedelta(days=7)).isoformat()
        return start, end
    return _range_from_context(ctx, key)


def _month_range(ctx: Any, key: str) -> tuple[str, str] | None:
    if key == "month_after_next":
        today = _context_today(ctx)
        year, month = _shift_month(today.year, today.month, 2)
        return _month_bounds(year, month)
    return _range_from_context(ctx, key)


def _single_relative_day(ctx: Any, key: str) -> str | None:
    if key == "day_before_yesterday":
        return (_context_today(ctx) - timedelta(days=2)).isoformat()
    if key == "day_after_after_tomorrow":
        return (_context_today(ctx) + timedelta(days=3)).isoformat()
    if isinstance(ctx, dict):
        ranges = ctx.get("ranges") if isinstance(ctx.get("ranges"), dict) else {}
        value = ranges.get(key) if isinstance(ranges.get(key), dict) else {}
        start = str(value.get("start_date") or "").strip()
        end = str(value.get("end_date") or "").strip()
        if DATE_RE.fullmatch(start) and start == end:
            return start
        direct = str(ctx.get(key) or "").strip()
        return direct if DATE_RE.fullmatch(direct) else None
    direct = str(getattr(ctx, key, "") or "").strip()
    return direct if DATE_RE.fullmatch(direct) else None


def _parse_absolute_dates(expression: str, ctx: Any) -> list[dict[str, str]]:
    text = str(expression or "")
    today = _context_today(ctx)
    items: list[dict[str, str]] = []
    occupied: set[tuple[int, int]] = set()
    for match in DATE_RE.finditer(text):
        try:
            day = date.fromisoformat(match.group(0)).isoformat()
        except ValueError:
            continue
        items.append(_resolved_item(match.group(0), day))
        occupied.add(match.span())
    for match in ZH_DATE_RE.finditer(text):
        if any(match.start() >= start and match.end() <= end for start, end in occupied):
            continue
        raw_year, raw_month, raw_day = match.groups()
        year = int(raw_year) if raw_year else today.year
        month = int(raw_month)
        day_num = int(raw_day)
        try:
            day = date(year, month, day_num).isoformat()
        except ValueError:
            continue
        items.append(_resolved_item(match.group(0), day))
    return items


_RELATIVE_DAY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("day_after_after_tomorrow", ("大后天",)),
    ("day_after_tomorrow", ("后天", "day after tomorrow", "the day after tomorrow")),
    ("tomorrow", ("明天", "明日", "tomorrow")),
    ("today", ("今天", "今日", "现在", "当前", "today")),
    ("yesterday", ("昨天", "昨日", "yesterday")),
    ("day_before_yesterday", ("前天",)),
)

_RELATIVE_RANGE_PATTERNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("next_next_week", "下下周", ("下下周", "再下一周", "week after next")),
    ("next_week", "下周", ("下周", "next week")),
    ("last_week", "上周", ("上周", "last week")),
    ("this_week", "本周", ("本周", "这周", "this week")),
    ("month_after_next", "下下月", ("下下个月", "下下月", "再下个月", "month after next")),
    ("next_month", "下月", ("下个月", "下月", "next month")),
    ("last_month", "上月", ("上个月", "上月", "last month")),
    ("this_month", "本月", ("本月", "这个月", "this month")),
)

_WEEK_PREFIX_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("next_next_week", ("下下周", "再下一周", "再下个", "再下一个")),
    ("next_week", ("下周", "下个", "下一个", "下一")),
    ("last_week", ("上周",)),
    ("this_week", ("本周", "这周", "这个", "这一个")),
)


def _spans_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _claim_non_overlapping_hits(candidates: list[tuple[int, int, str, Any]]) -> list[tuple[int, int, str, Any]]:
    occupied: list[tuple[int, int]] = []
    selected: list[tuple[int, int, str, Any]] = []
    for start, end, label, payload in sorted(candidates, key=lambda item: (-(item[1] - item[0]), item[0])):
        span = (start, end)
        if any(_spans_overlap(span, existing) for existing in occupied):
            continue
        occupied.append(span)
        selected.append((start, end, label, payload))
    return sorted(selected, key=lambda item: item[0])


def _zh_number_to_int(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    mapping = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if text in mapping:
        return mapping[text]
    if text == "十":
        return 10
    if text.startswith("十") and len(text) == 2 and text[1] in mapping:
        return 10 + mapping[text[1]]
    if text.endswith("十") and len(text) == 2 and text[0] in mapping:
        return mapping[text[0]] * 10
    if "十" in text:
        left, right = text.split("十", 1)
        if left in mapping and right in mapping:
            return mapping[left] * 10 + mapping[right]
    return None


def _extract_start_minutes(text: str) -> int | None:
    match = re.search(r"\b([01]?\d|2[0-3])[:：]([0-5]\d)\b", text)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    match = re.search(r"(凌晨|早上|上午|中午|下午|晚上|晚间)?\s*([零〇一二两三四五六七八九十\d]{1,3})\s*点(?:\s*([0-5]?\d)\s*分?)?", text)
    if not match:
        return None
    period = str(match.group(1) or "")
    hour = _zh_number_to_int(str(match.group(2) or ""))
    if hour is None or hour > 24:
        return None
    minute = int(match.group(3) or 0)
    if period in {"下午", "晚上", "晚间"} and hour < 12:
        hour += 12
    elif period == "中午" and hour < 11:
        hour += 12
    if hour == 24:
        hour = 0
    return hour * 60 + minute


def _is_create_context(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in ("create", "calendar create", "创建", "新增", "新建", "加一个"))


def _bare_weekday_date(ctx: Any, weekday_index: int, text: str) -> str:
    today = _context_today(ctx)
    monday = today - timedelta(days=today.weekday())
    target = monday + timedelta(days=weekday_index)
    if not _is_create_context(text):
        return target.isoformat()
    start_minutes = _extract_start_minutes(text)
    current_minutes = _context_current_minutes(ctx)
    if target < today or (target == today and start_minutes is not None and current_minutes is not None and start_minutes <= current_minutes):
        target += timedelta(days=7)
    return target.isoformat()


def _parse_weekday_dates(expression: str, ctx: Any) -> list[tuple[int, int, dict[str, str]]]:
    text = str(expression or "")
    candidates: list[tuple[int, int, str, dict[str, str]]] = []
    suffixes = (
        (0, ("一", "1")),
        (1, ("二", "2")),
        (2, ("三", "3")),
        (3, ("四", "4")),
        (4, ("五", "5")),
        (5, ("六", "6")),
        (6, ("日", "天", "7")),
    )
    for range_key, prefixes in _WEEK_PREFIX_KEYS:
        selected = _week_range(ctx, range_key)
        if not selected:
            continue
        start = date.fromisoformat(selected[0])
        for weekday_index, aliases in suffixes:
            pattern = (
                r"("
                + "|".join(re.escape(prefix) for prefix in prefixes)
                + r")\s*(?:周|星期|礼拜)?("
                + "|".join(re.escape(alias) for alias in aliases)
                + r")"
            )
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                label = match.group(0).replace(" ", "")
                day = (start + timedelta(days=weekday_index)).isoformat()
                candidates.append((match.start(), match.end(), label, _resolved_item(label, day)))

    suffix_map = {
        "一": 0,
        "1": 0,
        "二": 1,
        "2": 1,
        "三": 2,
        "3": 2,
        "四": 3,
        "4": 3,
        "五": 4,
        "5": 4,
        "六": 5,
        "6": 5,
        "日": 6,
        "天": 6,
        "7": 6,
    }
    bare_pattern = r"(?<![上下本这再])(?:周|星期|礼拜)\s*(一|二|三|四|五|六|日|天|[1-7])"
    for match in re.finditer(bare_pattern, text, flags=re.IGNORECASE):
        suffix = match.group(1)
        weekday_index = suffix_map.get(suffix)
        if weekday_index is None:
            continue
        label = match.group(0).replace(" ", "")
        day = _bare_weekday_date(ctx, weekday_index, text)
        candidates.append((match.start(), match.end(), label, _resolved_item(label, day)))

    return [(start, end, item) for start, end, _label, item in _claim_non_overlapping_hits(candidates)]


def _parse_relative_days(expression: str, ctx: Any) -> list[tuple[int, dict[str, str]]]:
    original = str(expression or "")
    text = original.lower()
    candidates: list[tuple[int, int, str, dict[str, str]]] = []
    for key, aliases in _RELATIVE_DAY_PATTERNS:
        day = _single_relative_day(ctx, key)
        if not day:
            continue
        for alias in aliases:
            start = 0
            while True:
                index = text.find(alias.lower(), start)
                if index < 0:
                    break
                label = original[index : index + len(alias)] or alias
                candidates.append((index, index + len(alias), label, _resolved_item(label, day)))
                start = index + max(1, len(alias))
    return [(start, item) for start, _end, _label, item in _claim_non_overlapping_hits(candidates)]


def _parse_ranges(expression: str, ctx: Any) -> list[tuple[int, dict[str, str]]]:
    text = str(expression or "").lower()
    candidates: list[tuple[int, int, str, dict[str, str]]] = []
    for key, label, aliases in _RELATIVE_RANGE_PATTERNS:
        selected = _week_range(ctx, key) if "week" in key else _month_range(ctx, key)
        if not selected:
            continue
        for alias in aliases:
            start = 0
            while True:
                index = text.find(alias.lower(), start)
                if index < 0:
                    break
                candidates.append((index, index + len(alias), label, _resolved_item(label, selected[0], selected[1])))
                start = index + max(1, len(alias))
    return [(start, item) for start, _end, _label, item in _claim_non_overlapping_hits(candidates)]


def resolve_time_expression(expression: str | None, time_context: Any, reference_text: str = "") -> dict[str, Any]:
    """Resolve user-facing time text into the single runtime date shape.

    The planner preserves raw phrases such as "明天" or "下周三". This function
    is the only deterministic place that converts those phrases to concrete ISO
    dates and program-computed weekday labels.
    """

    text = " ".join(str(value or "").strip() for value in (expression, reference_text) if str(value or "").strip())
    if not text:
        return _empty_resolved_time()

    weekday_hits = _parse_weekday_dates(text, time_context)
    occupied_labels = "".join(item["label"] for _, _, item in weekday_hits)
    absolute_items = _parse_absolute_dates(text, time_context)
    relative_day_hits = _parse_relative_days(text, time_context)
    range_hits = _parse_ranges(text, time_context)

    filtered_range_hits: list[tuple[int, dict[str, str]]] = []
    for index, item in range_hits:
        label = str(item.get("label") or "")
        if label and label in occupied_labels:
            continue
        filtered_range_hits.append((index, item))

    structured_hits = [
        (start, item)
        for start, _end, item in weekday_hits
    ] + [(max(0, text.find(str(item.get("label") or ""))), item) for item in absolute_items]
    ordered_hits = sorted(structured_hits + relative_day_hits + filtered_range_hits, key=lambda pair: pair[0])
    items = _dedupe_items([item for _, item in ordered_hits])
    if not items:
        return _empty_resolved_time()
    if len(items) > 1:
        return {"kind": "multi", "items": items}
    only = items[0]
    kind = "range" if only.get("start_date") != only.get("end_date") else "date"
    return {"kind": kind, "items": items}


def normalize_time_requirement(value: Any) -> dict[str, Any]:
    """Normalize the small validation-only time contract.

    New execution uses ``time_expression`` plus ``resolve_time_expression``.
    This helper remains only so calendar validators can reason about whether a
    date requirement exists without reviving old planner date-repair logic.
    """

    value = value if isinstance(value, dict) else {}
    time_expression = str(value.get("time_expression") or "").strip() or None
    absolute_date = str(value.get("absolute_date") or value.get("date") or "").strip() or None
    if absolute_date and not DATE_RE.fullmatch(absolute_date):
        absolute_date = None
    date_range = value.get("date_range") if isinstance(value.get("date_range"), dict) else None
    if date_range:
        start = str(date_range.get("start_date") or "").strip()
        end = str(date_range.get("end_date") or "").strip()
        date_range = {"start_date": start, "end_date": end} if DATE_RE.fullmatch(start) and DATE_RE.fullmatch(end) else None
    time_type = str(value.get("time_reference_type") or "").strip()
    if not time_type:
        if date_range:
            time_type = "range"
        elif absolute_date:
            time_type = "absolute"
        elif time_expression:
            time_type = "relative"
        else:
            time_type = "none"
    if time_type not in {"none", "relative", "absolute", "range", "ambiguous"}:
        time_type = "none"
    requires_current = bool(value.get("requires_current_datetime") or value.get("needs_current_datetime"))
    if time_expression or time_type in {"relative", "ambiguous"}:
        requires_current = True
    return {
        "has_time_requirement": bool(value.get("has_time_requirement") or time_type != "none" or time_expression),
        "time_reference_type": time_type,
        "time_expression": time_expression,
        "absolute_date": absolute_date if time_type == "absolute" else None,
        "date_range": date_range if time_type == "range" else None,
        "requires_current_datetime": requires_current,
        "needs_current_datetime": requires_current,
    }
