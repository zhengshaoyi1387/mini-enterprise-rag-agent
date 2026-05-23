from __future__ import annotations

import re
from typing import Any


CALENDAR_UPDATE_FIELDS = ("title", "type", "date", "time", "department", "location", "description")
GENERIC_CALENDAR_TITLE_SELECTORS = {"会议", "公司会议", "日程", "公司日程", "安排", "活动", "事件"}


def _clean_calendar_selector(selector: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(selector or {})
    title = str(cleaned.get("title") or "").strip()
    if title in GENERIC_CALENDAR_TITLE_SELECTORS:
        cleaned.pop("title", None)
    title_contains = str(cleaned.get("title_contains") or cleaned.get("title_keyword") or "").strip()
    if title_contains in GENERIC_CALENDAR_TITLE_SELECTORS:
        cleaned.pop("title_contains", None)
        cleaned.pop("title_keyword", None)
    return cleaned


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def compact_calendar_events(value: Any, limit: int = 20) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event in coerce_list(value)[:limit]:
        if not isinstance(event, dict):
            continue
        compact = {
            key: event.get(key)
            for key in ("event_id", "date", "weekday_zh", "time", "title", "location", "type", "department")
            if event.get(key) not in (None, "", [], {})
        }
        if compact:
            events.append(compact)
    return events


def is_calendar_delete_task(task: dict[str, Any]) -> bool:
    if str(task.get("kind") or "").lower() != "tool":
        return False
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    tool_name = str(task.get("tool") or task.get("tool_name") or "").strip()
    action = str(task.get("action") or tool_input.get("action") or "").strip().lower()
    return tool_name == "manage_company_calendar" and action == "delete"


def is_calendar_update_task(task: dict[str, Any]) -> bool:
    if str(task.get("kind") or "").lower() != "tool":
        return False
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    tool_name = str(task.get("tool") or task.get("tool_name") or "").strip()
    action = str(task.get("action") or tool_input.get("action") or "").strip().lower()
    return tool_name == "manage_company_calendar" and action == "update"


def is_unresolved_calendar_event_id(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return True
    text = str(value or "").strip()
    if not text:
        return True
    lower = text.lower()
    if lower in {"all", "*", "全部", "所有", "event_id", "event_ids", "multiple", "many", "unknown", "placeholder"}:
        return True
    if lower.startswith("event_id_from_"):
        return True
    if lower.endswith(".event_id") or "result.event_id" in lower:
        return True
    if "event" in lower and "from" in lower and not lower.startswith("evt-"):
        return True
    return not bool(re.fullmatch(r"EVT-\d{8}-\d{4}", text))


def inherit_calendar_event_ids_from_previous_context(state: dict[str, Any], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous = state.get("previous_tool_context") if isinstance(state.get("previous_tool_context"), dict) else {}
    if not previous:
        return tasks
    if previous.get("domain") != "calendar" and previous.get("tool_name") != "manage_company_calendar":
        return tasks
    if any(
        isinstance(task, dict)
        and str(task.get("kind") or "").lower() == "tool"
        and str(task.get("tool") or task.get("tool_name") or "") == "manage_company_calendar"
        and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() == "query"
        for task in tasks
    ):
        return tasks
    inherited_event_id = _previous_context_single_event_id(previous)
    if not inherited_event_id:
        return tasks
    changed = False
    output: list[dict[str, Any]] = []
    for task in tasks:
        candidate = dict(task)
        tool = str(candidate.get("tool") or candidate.get("tool_name") or "")
        tool_input = dict(candidate.get("tool_input") or {}) if isinstance(candidate.get("tool_input"), dict) else {}
        action = str(candidate.get("action") or tool_input.get("action") or "").lower()
        if (
            candidate.get("kind") == "tool"
            and tool == "manage_company_calendar"
            and action == "update"
            and is_unresolved_calendar_event_id(tool_input.get("event_id"))
        ):
            tool_input["event_id"] = inherited_event_id
            tool_input["_inherited_event_id_from_previous_context"] = True
            candidate["tool_input"] = tool_input
            changed = True
        output.append(candidate)
    if changed:
        state.setdefault("observations", []).append(
            {
                "type": "calendar_previous_context_event_id_inherited",
                "event_id": inherited_event_id,
                "task_ids": [task.get("task_id") for task in output if isinstance(task, dict)],
            }
        )
    return output if changed else tasks


def _previous_context_single_event_id(previous: dict[str, Any]) -> str:
    tool_input = previous.get("tool_input") if isinstance(previous.get("tool_input"), dict) else {}
    candidate = tool_input.get("event_id")
    if not is_unresolved_calendar_event_id(candidate):
        return str(candidate).strip()
    event = previous.get("event") if isinstance(previous.get("event"), dict) else {}
    candidate = event.get("event_id")
    if not is_unresolved_calendar_event_id(candidate):
        return str(candidate).strip()
    events = [item for item in (previous.get("events") or []) if isinstance(item, dict)]
    if len(events) == 1 and not is_unresolved_calendar_event_id(events[0].get("event_id")):
        return str(events[0].get("event_id")).strip()
    return ""


def flatten_calendar_update_fields(payload: dict[str, Any]) -> None:
    action = str(payload.get("action") or "").strip().lower()
    if action != "update":
        return
    for key in ("pending_update", "fields"):
        fields = payload.pop(key, None)
        if not isinstance(fields, dict):
            continue
        for field in CALENDAR_UPDATE_FIELDS:
            if field in fields and field not in payload:
                payload[field] = fields[field]


def calendar_update_selector(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("selector", "event_selector", "target", "match"):
        value = payload.get(key)
        if isinstance(value, dict):
            return dict(value)
    return {}


def sanitize_unresolved_event_selector(selector: dict[str, Any]) -> dict[str, Any]:
    cleaned = _clean_calendar_selector(dict(selector or {}))
    for key in ("event_id", "event_ids"):
        if key in cleaned and is_unresolved_calendar_event_id(cleaned.get(key)):
            cleaned.pop(key, None)
    return cleaned


def infer_selector_from_task_text(task: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(task.get(key) or "") for key in ("objective", "query", "instruction"))
    selector: dict[str, Any] = {}
    if any(token in text for token in ("第一个", "第一条", "首个", "第 1 个", "第1个")):
        selector["ordinal"] = "first"
    elif any(token in text for token in ("第二个", "第二条", "第 2 个", "第2个")):
        selector["ordinal"] = "2"
    elif any(token in text for token in ("最后一个", "最后一条")):
        selector["ordinal"] = "last"
    if "全部" in text or "所有" in text:
        selector["ordinal"] = "all"
    return selector


def event_matches_selector(event: dict[str, Any], selector: dict[str, Any]) -> bool:
    date_range = selector.get("date_range")
    if isinstance(date_range, dict):
        start = str(date_range.get("start_date") or "").strip()
        end = str(date_range.get("end_date") or "").strip()
        event_date = str(event.get("date") or "").strip()
        if start and event_date < start:
            return False
        if end and event_date > end:
            return False
    for key in ("event_id", "date", "weekday_zh", "time", "title", "type", "event_type", "department"):
        expected = selector.get(key)
        if expected in (None, "", [], {}):
            continue
        actual_key = "type" if key == "event_type" else key
        actual = str(event.get(actual_key) or "").strip()
        expected_text = str(expected).strip()
        if actual_key == "title" and expected_text in GENERIC_CALENDAR_TITLE_SELECTORS:
            continue
        if actual != expected_text:
            return False
    title_contains = str(selector.get("title_contains") or selector.get("title_keyword") or "").strip()
    if title_contains and title_contains not in str(event.get("title") or ""):
        return False
    return True


def select_calendar_events(events: list[dict[str, Any]], selector: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    candidates = [event for event in events if event_matches_selector(event, selector)]
    if not candidates:
        return [], False
    ordinal = str(selector.get("ordinal") or selector.get("position") or selector.get("select") or "").strip().lower()
    if len(candidates) == 1:
        return candidates, True
    if ordinal in {"first", "1", "第一个", "第一条"}:
        return [candidates[0]], True
    if ordinal in {"second", "2", "第二个", "第二条"}:
        return ([candidates[1]], True) if len(candidates) >= 2 else ([], False)
    if ordinal in {"last", "最后一个", "最后一条"}:
        return [candidates[-1]], True
    if ordinal in {"all", "全部", "所有"}:
        return candidates, True
    return candidates, False


def calendar_all_selector_requested(tool_input: dict[str, Any], task: dict[str, Any] | None = None) -> bool:
    raw_values = [
        tool_input.get("event_id"),
        tool_input.get("event_ids"),
        tool_input.get("select"),
        tool_input.get("ordinal"),
        tool_input.get("position"),
    ]
    if task:
        raw_values.extend([task.get("select"), task.get("ordinal"), task.get("position"), task.get("objective")])
    selector = calendar_update_selector(tool_input)
    if selector:
        raw_values.extend([selector.get("select"), selector.get("ordinal"), selector.get("position")])
    for value in raw_values:
        if isinstance(value, (list, tuple, set)):
            continue
        text = str(value or "").strip().lower()
        if text in {"all", "全部", "所有"} or "所有" in text or "全部" in text:
            return True
    return False


def latest_calendar_query_events(state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    for result in reversed(state.get("task_results") or []):
        if not isinstance(result, dict):
            continue
        if result.get("tool_name") != "manage_company_calendar" or result.get("action") != "query":
            continue
        tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
        events = [event for event in coerce_list(tool_result.get("events")) if isinstance(event, dict)]
        return events, result, True

    for observation in reversed(state.get("observations") or []):
        if not isinstance(observation, dict):
            continue
        raw_result = observation.get("raw_result") if isinstance(observation.get("raw_result"), dict) else {}
        events = [event for event in coerce_list(raw_result.get("events")) if isinstance(event, dict)]
        if events:
            return events, {"tool_input": observation.get("tool_input") or {}, "tool_result": {"events": events}}, True

    context = state.get("previous_tool_context") if isinstance(state.get("previous_tool_context"), dict) else {}
    if context and context.get("tool_name") == "manage_company_calendar":
        events = [event for event in coerce_list(context.get("events")) if isinstance(event, dict)]
        if events:
            return events, {"tool_input": context.get("tool_input") or {}, "tool_result": {"events": events}}, True
    return [], {}, False


def enrich_selector_from_source_range(selector: dict[str, Any], source_result: dict[str, Any]) -> None:
    if not selector:
        return
    source_input = source_result.get("tool_input") if isinstance(source_result.get("tool_input"), dict) else {}
    start_date = str(source_input.get("start_date") or "").strip()
    end_date = str(source_input.get("end_date") or "").strip()
    selector_date = str(selector.get("date") or "").strip()
    if selector_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", selector_date) and start_date and end_date:
        selector.pop("date", None)
        selector.setdefault("date_range", {"start_date": start_date, "end_date": end_date})


def append_calendar_resolution_result(
    state: dict[str, Any],
    task: dict[str, Any],
    *,
    action: str,
    status: str,
    message: str,
    candidates: list[dict[str, Any]] | None = None,
) -> None:
    task_id = str(task.get("task_id") or f"calendar_{action}")
    if task_id in set(state.get("completed_tasks") or []):
        return
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    clean_input = {
        key: value
        for key, value in tool_input.items()
        if key not in {"query", "user_id", "role"} and not str(key).startswith("_")
    }
    result = {
        "action": action,
        "status": status,
        "message": message,
        "candidate_events": compact_calendar_events(candidates or [], limit=20),
    }
    state.setdefault("task_results", []).append(
        {
            "task_id": task_id,
            "kind": "tool",
            "objective": task.get("objective") or f"{'更新' if action == 'update' else '删除'}公司日程",
            "status": status,
            "tool_name": "manage_company_calendar",
            "action": action,
            "tool_input": clean_input,
            "tool_result": result,
            "tool_calls": [],
            "result_summary": message,
            "error_message": "",
        }
    )
    state.setdefault("completed_tasks", []).append(task_id)


class CalendarTaskResolver:
    """Resolve calendar write tasks into concrete single-event operations.

    The graph node should not know how calendar selectors map to event_id. This
    adapter owns the calendar write contract: update/delete accept one concrete
    event_id, condition-based writes must use query results or previous context.
    """

    def resolve_task_from_context(self, state: dict[str, Any], task: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve one current write task before a real tool call.

        This is used immediately before ``call_tool`` so ReAct cannot pass
        selectors such as ``{"ordinal": "first"}`` or placeholder event IDs
        into the calendar write tool. It reuses the batch resolver and then
        merges the resolved task back into the runtime queue.
        """

        if not (is_calendar_update_task(task) or is_calendar_delete_task(task)):
            return task
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        if not is_unresolved_calendar_event_id(tool_input.get("event_id")):
            resolved = dict(task)
            resolved_input = dict(tool_input)
            flatten_calendar_update_fields(resolved_input)
            resolved["tool_input"] = resolved_input
            return resolved

        original_queue = [dict(item) for item in (state.get("task_queue") or []) if isinstance(item, dict)]
        original_task_id = str(task.get("task_id") or "")
        before_results = len(state.get("task_results") or [])
        state["task_queue"] = [dict(task)]
        changed = self.resolve_updates(state) if is_calendar_update_task(task) else self.resolve_deletes(state)
        resolved_queue = [dict(item) for item in (state.get("task_queue") or []) if isinstance(item, dict)]

        latest_resolution = next(
            (item for item in reversed((state.get("task_results") or [])[before_results:]) if isinstance(item, dict)),
            {},
        )
        if original_queue:
            merged_queue: list[dict[str, Any]] = []
            replaced = False
            for candidate in original_queue:
                if str(candidate.get("task_id") or "") == original_task_id:
                    merged_queue.extend(resolved_queue)
                    replaced = True
                else:
                    merged_queue.append(candidate)
            if not replaced:
                merged_queue.extend(resolved_queue)
            state["task_queue"] = merged_queue
        else:
            state["task_queue"] = resolved_queue

        if changed and latest_resolution:
            return None
        if changed and resolved_queue:
            return resolved_queue[0]
        if not changed:
            source_events, _source_result, has_source = latest_calendar_query_events(state)
            if not has_source or not source_events:
                action = "update" if is_calendar_update_task(task) else "delete"
                append_calendar_resolution_result(
                    state,
                    task,
                    action=action,
                    status="needs_clarification",
                    message=f"缺少可安全解析的日程候选，请先查询并指定要{'更新' if action == 'update' else '删除'}的 event_id。",
                    candidates=[],
                )
                return None
        return task

    def resolve_updates(self, state: dict[str, Any]) -> bool:
        queue = [dict(task) for task in list(state.get("task_queue") or []) if isinstance(task, dict)]
        if not queue:
            return False
        source_events, source_result, has_source = latest_calendar_query_events(state)
        changed = False
        new_queue: list[dict[str, Any]] = []

        for task in queue:
            if not is_calendar_update_task(task):
                new_queue.append(task)
                continue
            tool_input = dict(task.get("tool_input") or {})
            flatten_calendar_update_fields(tool_input)
            event_id = tool_input.get("event_id")
            if not is_unresolved_calendar_event_id(event_id):
                task = dict(task)
                task["tool_input"] = tool_input
                new_queue.append(task)
                continue
            if not has_source:
                task = dict(task)
                task["tool_input"] = tool_input
                new_queue.append(task)
                continue

            # If the dependency query already narrowed the target to a single event,
            # trust that observation and inject its event_id. Do not re-filter it
            # with weak planner selectors such as title="公司会议"; that phrase is
            # an event type cue, not the real meeting title.
            if len(source_events) == 1 and not is_unresolved_calendar_event_id(source_events[0].get("event_id")):
                candidates, selected_is_safe = [source_events[0]], True
            else:
                selector = calendar_update_selector(tool_input)
                inferred_selector = infer_selector_from_task_text(task)
                if not selector:
                    selector = inferred_selector
                else:
                    for key, value in inferred_selector.items():
                        selector.setdefault(key, value)
                selector = sanitize_unresolved_event_selector(selector)
                enrich_selector_from_source_range(selector, source_result)
                candidates, selected_is_safe = select_calendar_events(source_events, selector)
            if not candidates:
                append_calendar_resolution_result(
                    state,
                    task,
                    action="update",
                    status="skipped",
                    message="没有匹配日程可更新。",
                    candidates=[],
                )
                changed = True
                continue
            if not selected_is_safe:
                append_calendar_resolution_result(
                    state,
                    task,
                    action="update",
                    status="needs_clarification",
                    message="匹配到多个日程，请指定要更新的 event_id 后再修改。",
                    candidates=candidates,
                )
                changed = True
                continue

            source_input = source_result.get("tool_input") if isinstance(source_result.get("tool_input"), dict) else {}
            file_path = tool_input.get("file_path") or source_input.get("file_path")
            original_task_id = str(task.get("task_id") or "calendar_update")
            for idx, event in enumerate(candidates, start=1):
                update_input = {
                    key: value
                    for key, value in tool_input.items()
                    if key not in {"event_id", "event_ids", "selector", "event_selector", "target", "match"} and not str(key).startswith("_")
                }
                update_input["action"] = "update"
                update_input["event_id"] = str(event.get("event_id") or "").strip()
                if file_path and "file_path" not in update_input:
                    update_input["file_path"] = file_path

                expanded = dict(task)
                expanded["task_id"] = original_task_id if idx == 1 else f"{original_task_id}_{idx}"
                expanded["action"] = "update"
                expanded["tool_input"] = update_input
                new_queue.append(expanded)
            changed = True

        if changed:
            state["task_queue"] = new_queue
            state.setdefault("observations", []).append({"type": "calendar_update_resolved", "remaining_task_count": len(new_queue)})
        return changed

    def resolve_deletes(self, state: dict[str, Any]) -> bool:
        queue = [dict(task) for task in list(state.get("task_queue") or []) if isinstance(task, dict)]
        if not queue:
            return False
        source_events, source_result, has_source = latest_calendar_query_events(state)
        changed = False
        new_queue: list[dict[str, Any]] = []

        for task in queue:
            if not is_calendar_delete_task(task):
                new_queue.append(task)
                continue
            tool_input = dict(task.get("tool_input") or {})
            if not is_unresolved_calendar_event_id(tool_input.get("event_id")):
                new_queue.append(task)
                continue
            if not has_source:
                new_queue.append(task)
                continue

            selector = calendar_update_selector(tool_input)
            inferred_selector = infer_selector_from_task_text(task)
            if not selector:
                selector = inferred_selector
            else:
                for key, value in inferred_selector.items():
                    selector.setdefault(key, value)
            selector = sanitize_unresolved_event_selector(selector)
            enrich_selector_from_source_range(selector, source_result)
            events = [event for event in source_events if str(event.get("event_id") or "").strip()]
            if selector:
                events, selected_is_safe = select_calendar_events(events, selector)
                if events and not selected_is_safe:
                    append_calendar_resolution_result(
                        state,
                        task,
                        action="delete",
                        status="needs_clarification",
                        message="匹配到多个日程，请指定要删除的 event_id 后再删除。",
                        candidates=events,
                    )
                    changed = True
                    continue
            elif len(events) > 1 and not calendar_all_selector_requested(tool_input, task):
                append_calendar_resolution_result(
                    state,
                    task,
                    action="delete",
                    status="needs_clarification",
                    message="匹配到多个日程，请指定要删除的 event_id 后再删除。",
                    candidates=events,
                )
                changed = True
                continue
            if not events:
                append_calendar_resolution_result(
                    state,
                    task,
                    action="delete",
                    status="skipped",
                    message="没有匹配日程可删除，无需删除。",
                    candidates=[],
                )
                changed = True
                continue

            source_input = source_result.get("tool_input") if isinstance(source_result.get("tool_input"), dict) else {}
            file_path = tool_input.get("file_path") or source_input.get("file_path")
            original_task_id = str(task.get("task_id") or "calendar_delete")
            for idx, event in enumerate(events, start=1):
                delete_input = {
                    key: value
                    for key, value in tool_input.items()
                    if key not in {"event_id", "event_ids"} and not str(key).startswith("_")
                }
                delete_input["action"] = "delete"
                delete_input["event_id"] = str(event.get("event_id") or "").strip()
                if file_path and "file_path" not in delete_input:
                    delete_input["file_path"] = file_path

                expanded = dict(task)
                expanded["task_id"] = original_task_id if idx == 1 else f"{original_task_id}_{idx}"
                expanded["action"] = "delete"
                expanded["tool_input"] = delete_input
                title = str(event.get("title") or "").strip()
                if title:
                    expanded["objective"] = f"删除日程：{title}"
                new_queue.append(expanded)
            changed = True

        if changed:
            state["task_queue"] = new_queue
            state.setdefault("observations", []).append({"type": "calendar_delete_resolved", "remaining_task_count": len(new_queue)})
        return changed
