from __future__ import annotations

import inspect

from mini_rag.capabilities.calendar.compiler import maybe_add_query_first_update_task
from mini_rag.capabilities.calendar.slots import infer_update_fields


def test_query_first_update_with_concrete_event_id_compiles_real_update_task() -> None:
    payload = {
        "selected_tool": "manage_company_calendar",
        "selected_action": "update",
        "standalone_query": "把不存在的 event_id EVT-20990101-9999 改成测试会议。",
    }
    tasks = [
        {
            "task_id": "t1",
            "kind": "tool",
            "objective": "查询 event_id EVT-20990101-9999 是否存在",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "event_id": "EVT-20990101-9999"},
        }
    ]

    changed = maybe_add_query_first_update_task(payload, tasks)

    assert changed is True
    assert tasks[-1]["action"] == "update"
    assert tasks[-1]["tool_input"]["event_id"] == "EVT-20990101-9999"
    assert tasks[-1]["tool_input"]["title"] == "测试会议"


def test_calendar_query_reason_does_not_create_write_task() -> None:
    payload = {
        "selected_tool": "manage_company_calendar",
        "selected_action": "query",
        "standalone_query": "查下周所有公司团建日程。",
        "reason": "event_type 设为 activity 表示团建活动",
    }
    tasks = [
        {
            "task_id": "t1",
            "kind": "tool",
            "objective": "查询下周所有公司团建日程",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query", "event_type": "activity"},
        }
    ]

    changed = maybe_add_query_first_update_task(payload, tasks)

    assert changed is False
    assert len(tasks) == 1


def test_calendar_compiler_does_not_own_domain_lexicon_or_slot_regexes() -> None:
    import mini_rag.capabilities.calendar.compiler as compiler

    source = inspect.getsource(compiler)

    assert "CALENDAR_QUERY_TERMS" not in source
    assert "UPDATE_VERBS" not in source
    assert "EVENT_TYPE_TERMS" not in source
    assert infer_update_fields("把会议地点改成会议室A") == {"location": "会议室A"}
