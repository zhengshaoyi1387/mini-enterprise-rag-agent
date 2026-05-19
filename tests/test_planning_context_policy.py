from __future__ import annotations

from types import SimpleNamespace

from mini_rag.planning.context_policy import build_planning_context, extract_previous_tool_context, turn_to_history_item


def test_extract_previous_tool_context_keeps_compact_safe_fields_only() -> None:
    turn = SimpleNamespace(
        trace={
            "trace_id": "trace-1",
            "current_tool_context": {
                "domain": "calendar",
                "tool_name": "manage_company_calendar",
                "tool_input": {
                    "action": "query",
                    "query": "raw user query",
                    "user_id": "u1",
                    "role": "employee",
                    "file_path": "/tmp/private",
                    "_debug": "hidden",
                    "start_date": "2026-05-18",
                },
                "result_summary": "x" * 900,
                "events": [
                    {
                        "event_id": "EVT-20260518-0001",
                        "date": "2026-05-18",
                        "weekday_zh": "星期一",
                        "time": "10:00-11:00",
                        "title": "周例会",
                        "location": "会议室A",
                        "description": "should not leak",
                    }
                ],
            },
        }
    )

    context = extract_previous_tool_context([turn])

    assert context["tool_input"] == {"action": "query", "start_date": "2026-05-18"}
    assert len(context["result_summary"]) == 700
    assert context["trace_id"] == "trace-1"
    assert context["events"] == [
        {
            "event_id": "EVT-20260518-0001",
            "date": "2026-05-18",
            "weekday_zh": "星期一",
            "time": "10:00-11:00",
            "title": "周例会",
            "location": "会议室A",
        }
    ]


def test_build_planning_context_compacts_history_and_tool_context() -> None:
    history = [
        {
            "question": "上一轮查日程",
            "standalone_query": "查询下周日程",
            "answer": "[source: noisy] 很长的回答" * 20,
            "intent": "daily_tool",
            "topic": "calendar",
        }
    ]
    previous_tool_context = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {"query": "remove", "role": "remove", "start_date": "2026-05-18"},
        "result_summary": "下周有 1 条日程",
    }

    context = build_planning_context(history=history, previous_tool_context=previous_tool_context)

    assert context["last_turn"]["user"] == "上一轮查日程"
    assert "source:" not in context["last_turn"]["assistant_brief"]
    assert context["previous_tool_context"]["tool_input"] == {"start_date": "2026-05-18"}
    assert len(context["previous_tool_context"]["result_summary"]) <= 220


def test_turn_to_history_item_uses_memory_answer_without_citations() -> None:
    turn = SimpleNamespace(
        question="问制度",
        standalone_query="问制度",
        answer="原始回答 [source: finance.md]",
        memory_answer="干净摘要",
        intent="rag_fact",
        topic="finance",
        entities=["报销"],
        created_at=123,
    )

    item = turn_to_history_item(turn)

    assert item["memory_answer"] == "干净摘要"
    assert item["answer"] == "原始回答 [source: finance.md]"
    assert item["entities"] == ["报销"]
