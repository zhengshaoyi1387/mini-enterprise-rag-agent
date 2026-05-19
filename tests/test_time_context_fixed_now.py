from __future__ import annotations

from pathlib import Path

from mini_rag.capabilities.datetime.service import build_time_context, datetime_payload_from_time_context
from mini_rag.tools.datetime_tool import get_current_datetime


def test_time_context_uses_eval_fixed_now_env(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_EVAL_FIXED_NOW", "2026-05-17 01:00:00 Asia/Shanghai")

    ctx = build_time_context(timezone="Asia/Shanghai")

    assert ctx.today == "2026-05-17"
    assert ctx.tomorrow == "2026-05-18"
    assert ctx.next_week.start_date == "2026-05-18"
    assert ctx.next_week.end_date == "2026-05-24"


def test_datetime_tool_uses_fixed_now_and_does_not_return_days(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_EVAL_FIXED_NOW", "2026-05-17T01:00:00+08:00")

    result = get_current_datetime({"timezone": "Asia/Shanghai"})

    assert result["current_date"] == "2026-05-17"
    assert result["weekday_zh"] == "星期日"
    assert result["ranges"]["tomorrow"] == {"start_date": "2026-05-18", "end_date": "2026-05-18"}
    assert result["ranges"]["next_week"] == {"start_date": "2026-05-18", "end_date": "2026-05-24"}
    assert "days" not in result
    assert all("days" not in value for value in result["ranges"].values())


def test_datetime_payload_from_time_context_is_compact(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_EVAL_FIXED_NOW", "2026-05-17 01:00:00 Asia/Shanghai")

    payload = datetime_payload_from_time_context(build_time_context(timezone="Asia/Shanghai"))

    assert payload["current_date"] == "2026-05-17"
    assert payload["ranges"]["last_week"] == {"start_date": "2026-05-04", "end_date": "2026-05-10"}
    assert "days" not in payload

