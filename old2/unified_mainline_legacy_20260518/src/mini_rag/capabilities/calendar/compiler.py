from __future__ import annotations

from typing import Any

from mini_rag.capabilities.calendar.resolver import is_unresolved_calendar_event_id
from mini_rag.capabilities.calendar.slots import (
    infer_event_id,
    infer_event_type,
    infer_ordinal_selector,
    infer_relative_event_queries,
    infer_update_fields,
    mentions_calendar_query,
    mentions_update_action,
)
from mini_rag.capabilities.datetime.resolver import normalize_time_requirement, relative_time_requirement


def _task_is_datetime(task: dict[str, Any]) -> bool:
    return (
        str(task.get("kind") or "").lower() == "tool"
        and str(task.get("tool") or "") == "get_current_datetime"
    )


def _task_is_calendar_query(task: dict[str, Any]) -> bool:
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    return (
        str(task.get("kind") or "").lower() == "tool"
        and str(task.get("tool") or "") == "manage_company_calendar"
        and str(task.get("action") or tool_input.get("action") or "").lower() == "query"
    )


def _task_is_calendar_write(task: dict[str, Any]) -> bool:
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    return (
        str(task.get("kind") or "").lower() == "tool"
        and str(task.get("tool") or "") == "manage_company_calendar"
        and str(task.get("action") or tool_input.get("action") or "").lower() in {"create", "update", "delete"}
    )


def maybe_add_calendar_query_task(payload: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    """Complete an executable plan when a datetime task masks a calendar query.

    The classifier can correctly identify a mixed request such as "current time
    plus tomorrow's meetings" but the planner may return only the datetime
    task. This compiler step is capability-level normalization: it uses the
    structured knowledge/time contract and generic calendar vocabulary to add
    the missing read task. It does not choose write targets or bypass
    validation.
    """

    if any(_task_is_calendar_query(task) for task in tasks if isinstance(task, dict)):
        return False
    if not any(_task_is_datetime(task) for task in tasks if isinstance(task, dict)):
        return False

    knowledge = payload.get("knowledge_requirement") if isinstance(payload.get("knowledge_requirement"), dict) else {}
    if knowledge.get("should_use_rag"):
        return False

    text = " ".join(
        str(payload.get(key) or "")
        for key in ("standalone_query", "question", "topic", "reason")
    )
    if not mentions_calendar_query(text):
        return False

    time_requirement = normalize_time_requirement(payload.get("time_requirement") if isinstance(payload.get("time_requirement"), dict) else {})
    if not (
        time_requirement.get("requires_current_datetime")
        or time_requirement.get("absolute_date")
        or time_requirement.get("date_range")
    ):
        return False

    datetime_dependencies = [str(task.get("task_id") or "") for task in tasks if isinstance(task, dict) and _task_is_datetime(task)]
    subqueries = infer_relative_event_queries(text)
    if subqueries:
        for item in subqueries:
            tasks.append(
                {
                    "task_id": f"t{len(tasks) + 1}",
                    "kind": "tool",
                    "objective": f"查询{item.objective}公司日程",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "event_type": item.event_type, "department": "all"},
                    "time_requirement": relative_time_requirement(item.relative),
                    "depends_on": datetime_dependencies,
                }
            )
    else:
        event_type = infer_event_type(text)
        tasks.append(
            {
                "task_id": f"t{len(tasks) + 1}",
                "kind": "tool",
                "objective": text or "查询公司日程安排",
                "tool": "manage_company_calendar",
                "action": "query",
                "tool_input": {"action": "query", "event_type": event_type, "department": "all"},
                "time_requirement": dict(time_requirement),
                "depends_on": datetime_dependencies,
            }
        )
    return True


def maybe_add_query_first_update_task(payload: dict[str, Any], tasks: list[dict[str, Any]]) -> bool:
    """Add a missing calendar update task after an explicit query task.

    This handles planner omissions for query-first updates. It only compiles a
    write task when the request text contains a generic update verb and at
    least one concrete write field can be extracted. Target resolution remains
    in the resolver, which enforces 0/1/many candidate safety.
    """

    if any(_task_is_calendar_write(task) for task in tasks if isinstance(task, dict)):
        return False
    query_task = next((task for task in tasks if isinstance(task, dict) and _task_is_calendar_query(task)), None)
    if not query_task:
        return False

    user_text = " ".join(
        str(payload.get(key) or "")
        for key in ("standalone_query", "question", "topic")
    )
    selected_action = str(payload.get("selected_action") or (payload.get("tool_input") or {}).get("action") or "").strip().lower()
    if selected_action != "update" and not mentions_update_action(user_text):
        return False
    update_fields = infer_update_fields(user_text)
    if not update_fields:
        return False

    query_input = query_task.get("tool_input") if isinstance(query_task.get("tool_input"), dict) else {}
    selector: dict[str, Any] = {}
    ordinal = infer_ordinal_selector(user_text)
    if ordinal:
        selector["ordinal"] = ordinal
    event_type = str(query_input.get("event_type") or infer_event_type(user_text) or "").strip()
    if event_type and event_type != "all":
        selector["event_type"] = event_type
    start_date = str(query_input.get("start_date") or "").strip()
    end_date = str(query_input.get("end_date") or "").strip()
    if start_date and end_date:
        selector["date_range"] = {"start_date": start_date, "end_date": end_date}

    update_input: dict[str, Any] = {"action": "update", **update_fields}
    event_id = str(query_input.get("event_id") or infer_event_id(user_text) or "").strip()
    if event_id and not is_unresolved_calendar_event_id(event_id):
        update_input["event_id"] = event_id
    if selector:
        update_input["selector"] = selector

    tasks.append(
        {
            "task_id": f"t{len(tasks) + 1}",
            "kind": "tool",
            "objective": user_text or "更新查询结果中的公司日程",
            "tool": "manage_company_calendar",
            "action": "update",
            "tool_input": update_input,
            "time_requirement": {"time_reference_type": "none", "requires_current_datetime": False},
            "depends_on": [str(query_task.get("task_id") or "")],
        }
    )
    return True
