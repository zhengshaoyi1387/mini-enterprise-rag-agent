from __future__ import annotations

from mini_rag.capabilities.datetime.resolver import resolve_time_expression
from mini_rag.capabilities.datetime.service import build_time_context


def fixed_context():
    return build_time_context(timezone="Asia/Shanghai", override_now="2026-05-18T09:30:00+08:00")


def late_monday_context():
    return build_time_context(timezone="Asia/Shanghai", override_now="2026-05-18T23:47:00+08:00")


def test_resolve_single_relative_days_with_weekday() -> None:
    ctx = fixed_context()

    result = resolve_time_expression("后天", ctx)

    assert result == {
        "kind": "date",
        "items": [
            {
                "label": "后天",
                "start_date": "2026-05-20",
                "end_date": "2026-05-20",
                "weekday_zh": "星期三",
            }
        ],
    }


def test_resolve_bare_weekday_aliases_from_current_week() -> None:
    ctx = fixed_context()

    for text in ("星期一", "周一", "礼拜一"):
        result = resolve_time_expression(text, ctx)
        assert result["kind"] == "date"
        assert result["items"][0]["start_date"] == "2026-05-18"
        assert result["items"][0]["weekday_zh"] == "星期一"

    result = resolve_time_expression("星期天", ctx)
    assert result["items"][0]["start_date"] == "2026-05-24"
    assert result["items"][0]["weekday_zh"] == "星期日"


def test_resolve_front_day_and_large_day_after_tomorrow_without_substring_multi() -> None:
    ctx = fixed_context()

    assert resolve_time_expression("前天", ctx)["items"][0]["start_date"] == "2026-05-16"

    result = resolve_time_expression("大后天", ctx)
    assert result == {
        "kind": "date",
        "items": [
            {
                "label": "大后天",
                "start_date": "2026-05-21",
                "end_date": "2026-05-21",
                "weekday_zh": "星期四",
            }
        ],
    }


def test_resolve_long_range_terms_without_substring_duplicates() -> None:
    ctx = fixed_context()

    next_next_week = resolve_time_expression("下下周", ctx)
    assert next_next_week == {
        "kind": "range",
        "items": [
            {
                "label": "下下周",
                "start_date": "2026-06-01",
                "end_date": "2026-06-07",
                "weekday_zh": "",
            }
        ],
    }

    next_next_month = resolve_time_expression("下下月", ctx)
    assert next_next_month == {
        "kind": "range",
        "items": [
            {
                "label": "下下月",
                "start_date": "2026-07-01",
                "end_date": "2026-07-31",
                "weekday_zh": "",
            }
        ],
    }


def test_create_context_bare_weekday_with_past_time_rolls_to_next_week() -> None:
    ctx = late_monday_context()

    result = resolve_time_expression("星期一晚上九点到十点", ctx, reference_text="calendar create 创建会议")

    assert result["kind"] == "date"
    assert result["items"][0]["start_date"] == "2026-05-25"
    assert result["items"][0]["weekday_zh"] == "星期一"


def test_resolve_weekday_expression_from_week_range() -> None:
    ctx = fixed_context()

    result = resolve_time_expression("下周三", ctx)

    assert result["kind"] == "date"
    assert result["items"][0]["label"] == "下周三"
    assert result["items"][0]["start_date"] == "2026-05-27"
    assert result["items"][0]["weekday_zh"] == "星期三"


def test_resolve_multi_time_expression_keeps_all_items() -> None:
    ctx = fixed_context()

    result = resolve_time_expression("今天、明天、下周一", ctx)

    assert result["kind"] == "multi"
    assert [(item["label"], item["start_date"], item["weekday_zh"]) for item in result["items"]] == [
        ("今天", "2026-05-18", "星期一"),
        ("明天", "2026-05-19", "星期二"),
        ("下周一", "2026-05-25", "星期一"),
    ]


def test_resolve_month_and_week_ranges() -> None:
    ctx = fixed_context()

    assert resolve_time_expression("本周", ctx)["items"][0] == {
        "label": "本周",
        "start_date": "2026-05-18",
        "end_date": "2026-05-24",
        "weekday_zh": "",
    }
    assert resolve_time_expression("下月", ctx)["items"][0] == {
        "label": "下月",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
        "weekday_zh": "",
    }


def test_resolve_absolute_dates_without_external_dependency() -> None:
    ctx = fixed_context()

    result = resolve_time_expression("5月21日", ctx)

    assert result == {
        "kind": "date",
        "items": [
            {
                "label": "5月21日",
                "start_date": "2026-05-21",
                "end_date": "2026-05-21",
                "weekday_zh": "星期四",
            }
        ],
    }
