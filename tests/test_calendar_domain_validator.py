from __future__ import annotations

from mini_rag.capabilities.calendar.validator import (
    calendar_write_needs_clarification,
    has_executable_calendar_query_source,
)
from mini_rag.capabilities.calendar.resolver import CalendarTaskResolver


def test_calendar_write_with_placeholder_event_id_needs_clarification_without_query_source() -> None:
    payload = {
        "selected_tool": "manage_company_calendar",
        "selected_action": "delete",
        "tool_input": {"action": "delete", "event_id": "event_id_from_previous_query"},
    }

    assert calendar_write_needs_clarification(payload, [], allowed_actions={"delete"}) is True


def test_calendar_write_permission_denial_is_not_reported_as_clarification() -> None:
    payload = {
        "selected_tool": "manage_company_calendar",
        "selected_action": "delete",
        "tool_input": {"action": "delete", "event_id": "event_id_from_previous_query"},
    }

    assert calendar_write_needs_clarification(payload, [], allowed_actions={"query"}) is False


def test_calendar_query_source_makes_query_first_write_resolvable() -> None:
    tasks = [
        {
            "task_id": "q1",
            "kind": "tool",
            "tool": "manage_company_calendar",
            "action": "query",
            "tool_input": {"action": "query"},
            "time_requirement": {
                "time_reference_type": "relative",
                "time_expression": "下周",
                "requires_current_datetime": True,
            },
        },
        {
            "task_id": "d1",
            "kind": "tool",
            "tool": "manage_company_calendar",
            "action": "delete",
            "tool_input": {"action": "delete", "event_id": "multiple"},
        },
    ]

    assert has_executable_calendar_query_source(tasks) is True
    assert calendar_write_needs_clarification({}, tasks, allowed_actions={"query", "delete"}) is False


def test_calendar_resolver_converts_result_event_id_placeholder_with_ordinal() -> None:
    state = {
        "task_results": [
            {
                "task_id": "q",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_input": {"start_date": "2026-05-18", "end_date": "2026-05-24"},
                "tool_result": {
                    "events": [
                        {"event_id": "EVT-20260519-0001", "date": "2026-05-19", "title": "公司团建"},
                        {"event_id": "EVT-20260521-0002", "date": "2026-05-21", "title": "公司团建"},
                    ]
                },
            }
        ],
        "task_queue": [
            {
                "task_id": "u",
                "kind": "tool",
                "objective": "更新第一个团建活动地点为多功能厅",
                "tool": "manage_company_calendar",
                "action": "update",
                "tool_input": {"action": "update", "selector": {"event_id": "q_result.event_id"}, "location": "多功能厅"},
            }
        ],
    }

    changed = CalendarTaskResolver().resolve_updates(state)

    assert changed is True
    assert state["task_queue"][0]["tool_input"]["event_id"] == "EVT-20260519-0001"
    assert state["task_queue"][0]["tool_input"]["location"] == "多功能厅"
