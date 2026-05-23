from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_rag.capabilities.calendar.resolver import CALENDAR_UPDATE_FIELDS, is_unresolved_calendar_event_id
from mini_rag.capabilities.datetime.resolver import resolve_time_expression


CALENDAR_EXPECTED_UPDATE_FIELDS = tuple(field for field in CALENDAR_UPDATE_FIELDS if field != "department") + ("department",)


@dataclass(frozen=True)
class CompletionCheckResult:
    status: str
    goal_type: str
    reason: str
    expected_result: dict[str, Any]
    observed_result: dict[str, Any]
    safe_next_action: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        output = {
            "status": self.status,
            "goal_type": self.goal_type,
            "reason": self.reason,
            "expected_result": self.expected_result,
            "observed_result": self.observed_result,
            "safe_next_action_source": "deterministic" if self.safe_next_action else "none",
        }
        if self.safe_next_action:
            output["safe_next_action"] = self.safe_next_action
        return output


def normalize_goal_contract(value: Any, *, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    explicit = value if isinstance(value, dict) else {}
    if explicit:
        target = dict(explicit.get("target") or {}) if isinstance(explicit.get("target"), dict) else {}
        expected = _clean_expected_result(explicit.get("expected_result"))
        expected = _sanitize_expected_result_against_plan(expected, plan or {})
        target.update(_target_from_calendar_query_tasks(plan or {}))
        goal = {
            "goal_type": str(explicit.get("goal_type") or "").strip(),
            "target": target,
            "expected_result": expected,
            "success_condition": dict(explicit.get("success_condition") or {}) if isinstance(explicit.get("success_condition"), dict) else {},
        }
        if goal["goal_type"]:
            return {key: val for key, val in goal.items() if val not in (None, "", [], {})}
    return derive_goal_contract_from_plan(plan or {})


def derive_goal_contract_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    tasks = [task for task in (plan.get("tasks") or []) if isinstance(task, dict)]
    update_tasks = [
        task
        for task in tasks
        if str(task.get("kind") or "").lower() == "tool"
        and str(task.get("tool") or task.get("tool_name") or "") == "manage_company_calendar"
        and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() == "update"
    ]
    if update_tasks:
        expected: dict[str, Any] = {}
        for task in update_tasks:
            expected.update(_expected_result_from_update_task(task))
        expected = _sanitize_expected_result_against_plan(expected, {"tasks": tasks})
        if not expected:
            return {}
        query_task = next(
            (
                task
                for task in tasks
                if str(task.get("kind") or "").lower() == "tool"
                and str(task.get("tool") or task.get("tool_name") or "") == "manage_company_calendar"
                and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() == "query"
            ),
            {},
        )
        query_input = query_task.get("tool_input") if isinstance(query_task.get("tool_input"), dict) else {}
        target = {
            key: query_input.get(key)
            for key in ("event_type", "department", "start_date", "end_date")
            if query_input.get(key) not in (None, "", [], {})
        }
        if query_task.get("time_expression"):
            target["time_expression"] = query_task.get("time_expression")
        return {
            "goal_type": "calendar_update",
            "target": target,
            "expected_result": expected,
            "success_condition": {
                "required_tool": "manage_company_calendar",
                "required_action": "update",
                "required_status": "updated",
                "updated_fields_must_match": True,
            },
        }

    rag_tasks = [task for task in tasks if str(task.get("kind") or "").lower() == "rag"]
    tool_tasks = [task for task in tasks if str(task.get("kind") or "").lower() == "tool"]
    if rag_tasks and tool_tasks:
        return {"goal_type": "mixed", "expected_result": {}, "success_condition": {}}
    if rag_tasks:
        return {"goal_type": "rag_answer", "expected_result": {}, "success_condition": {}}
    if tool_tasks:
        first = tool_tasks[0]
        return {
            "goal_type": "skill_analysis" if str(first.get("tool") or first.get("tool_name") or "") == "skill" else "tool_query",
            "target": {
                "tool_name": first.get("tool") or first.get("tool_name"),
                "action": first.get("action") or (first.get("tool_input") or {}).get("action"),
            },
            "expected_result": {},
            "success_condition": {},
        }
    return {}


def resolve_goal_contract_time(goal_contract: dict[str, Any], time_context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(goal_contract, dict) or not goal_contract:
        return {}
    output = {
        "goal_type": goal_contract.get("goal_type"),
        "target": dict(goal_contract.get("target") or {}) if isinstance(goal_contract.get("target"), dict) else {},
        "expected_result": dict(goal_contract.get("expected_result") or {}) if isinstance(goal_contract.get("expected_result"), dict) else {},
        "success_condition": dict(goal_contract.get("success_condition") or {}) if isinstance(goal_contract.get("success_condition"), dict) else {},
    }
    if output.get("goal_type") != "calendar_update":
        return {key: val for key, val in output.items() if val not in (None, "", [], {})}

    expected = output["expected_result"]
    date_expression = str(expected.get("date_expression") or "").strip()
    if date_expression and not expected.get("date"):
        resolved = resolve_time_expression(date_expression, time_context, reference_text="calendar_update expected_result")
        items = [item for item in (resolved.get("items") or []) if isinstance(item, dict)]
        if items:
            start = str(items[0].get("start_date") or "").strip()
            end = str(items[0].get("end_date") or start).strip()
            if start and start == end:
                expected["date"] = start
                output["expected_result_resolved_time"] = resolved
    return {key: val for key, val in output.items() if val not in (None, "", [], {})}


def check_goal_completion(state: dict[str, Any], goal_contract: dict[str, Any] | None = None) -> CompletionCheckResult:
    goal = goal_contract if isinstance(goal_contract, dict) else {}
    goal_type = str(goal.get("goal_type") or "").strip()
    if not goal_type:
        return CompletionCheckResult("completed", "none", "no_goal_contract", {}, {})
    if goal_type == "calendar_update":
        return _check_calendar_update_completion(state, goal)
    if goal_type == "skill_analysis":
        return _check_skill_completion(state, goal)
    if goal_type == "rag_answer":
        return _check_rag_completion(state, goal)
    if goal_type == "mixed":
        rag = _check_rag_completion(state, goal)
        if rag.status in {"failed", "unsupported"}:
            return CompletionCheckResult("partial", "mixed", rag.reason, rag.expected_result, rag.observed_result)
        return CompletionCheckResult("completed", "mixed", "mixed_goal_checked_lightly", {}, {})
    return _check_tool_query_completion(state, goal)


def _clean_expected_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: val
        for key, val in value.items()
        if key in set(CALENDAR_EXPECTED_UPDATE_FIELDS) | {"date_expression"} and val not in (None, "", [], {})
    }


def _expected_result_from_update_task(task: dict[str, Any]) -> dict[str, Any]:
    tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
    expected: dict[str, Any] = {}
    pending = tool_input.get("pending_update") if isinstance(tool_input.get("pending_update"), dict) else {}
    source = pending or tool_input
    for field in CALENDAR_EXPECTED_UPDATE_FIELDS:
        if field == "title" and not _task_explicitly_updates_title(task):
            continue
        if field in source and source.get(field) not in (None, "", [], {}):
            expected[field] = source.get(field)
    date_expression = pending.get("date_expression") or tool_input.get("date_expression")
    if date_expression not in (None, "", [], {}) and not any(field in expected for field in CALENDAR_EXPECTED_UPDATE_FIELDS if field != "date"):
        expected["date_expression"] = date_expression
    if not expected:
        expression = str(task.get("time_expression") or "").strip()
        if expression:
            expected["date_expression"] = expression
    return _clean_expected_result(expected)


def _drop_query_date_expression_from_non_date_expected_result(expected: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    date_expression = str(expected.get("date_expression") or "").strip()
    if not date_expression:
        return expected
    has_non_date_field = any(field in expected for field in CALENDAR_EXPECTED_UPDATE_FIELDS if field != "date")
    if not has_non_date_field:
        return expected
    query_expressions = _calendar_query_time_expressions(plan)
    if date_expression not in query_expressions:
        return expected
    cleaned = dict(expected)
    cleaned.pop("date_expression", None)
    return cleaned


def _drop_query_selector_fields_from_expected_result(expected: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    if not any(field in expected for field in ("type", "department")):
        return expected
    has_real_update_field = any(field in expected for field in ("title", "date", "time", "location", "description", "date_expression"))
    if not has_real_update_field:
        return expected
    query_selectors = _calendar_query_selectors(plan)
    cleaned = dict(expected)
    if cleaned.get("type") not in (None, "", [], {}) and str(cleaned.get("type")) == str(query_selectors.get("event_type") or ""):
        cleaned.pop("type", None)
    if cleaned.get("department") not in (None, "", [], {}) and str(cleaned.get("department")) == str(query_selectors.get("department") or ""):
        cleaned.pop("department", None)
    return cleaned


def _task_explicitly_updates_title(task: dict[str, Any]) -> bool:
    text = f"{task.get('objective') or ''}\n{task.get('query') or ''}"
    return any(token in text for token in ("标题", "名称", "命名"))


def _sanitize_expected_result_against_plan(expected: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    cleaned = _drop_query_date_expression_from_non_date_expected_result(dict(expected), plan)
    cleaned = _drop_query_selector_fields_from_expected_result(cleaned, plan)
    cleaned = _drop_query_title_from_non_title_update(cleaned, plan)
    return cleaned


def _drop_query_title_from_non_title_update(expected: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    title = str(expected.get("title") or "").strip()
    if not title:
        return expected
    has_other_update = any(field in expected for field in ("time", "location", "date", "date_expression", "description", "type"))
    if not has_other_update:
        return expected
    update_tasks = [task for task in (plan.get("tasks") or []) if isinstance(task, dict) and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() == "update"]
    if any(_task_explicitly_updates_title(task) for task in update_tasks):
        return expected
    query_titles = _calendar_query_titles(plan)
    if not query_titles or title in query_titles:
        cleaned = dict(expected)
        cleaned.pop("title", None)
        return cleaned
    return expected


def _target_from_calendar_query_tasks(plan: dict[str, Any]) -> dict[str, Any]:
    target: dict[str, Any] = {}
    for task in plan.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if str(task.get("kind") or "").lower() != "tool":
            continue
        if str(task.get("tool") or task.get("tool_name") or "") != "manage_company_calendar":
            continue
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        if str(task.get("action") or tool_input.get("action") or "").lower() != "query":
            continue
        for key in ("event_type", "department", "title", "start_date", "end_date"):
            if tool_input.get(key) not in (None, "", [], {}):
                target.setdefault(key, tool_input.get(key))
        if task.get("time_expression") not in (None, "", [], {}):
            target.setdefault("time_expression", task.get("time_expression"))
    return target


def _calendar_query_titles(plan: dict[str, Any]) -> set[str]:
    titles: set[str] = set()
    for task in plan.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if str(task.get("kind") or "").lower() != "tool":
            continue
        if str(task.get("tool") or task.get("tool_name") or "") != "manage_company_calendar":
            continue
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        if str(task.get("action") or tool_input.get("action") or "").lower() != "query":
            continue
        title = str(tool_input.get("title") or "").strip()
        if title:
            titles.add(title)
    return titles


def _calendar_query_time_expressions(plan: dict[str, Any]) -> set[str]:
    expressions: set[str] = set()
    for task in plan.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if str(task.get("kind") or "").lower() != "tool":
            continue
        if str(task.get("tool") or task.get("tool_name") or "") != "manage_company_calendar":
            continue
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        if str(task.get("action") or tool_input.get("action") or "").lower() != "query":
            continue
        for value in (task.get("time_expression"), task.get("date_expression"), tool_input.get("date_expression")):
            text = str(value or "").strip()
            if text:
                expressions.add(text)
    return expressions


def _calendar_query_selectors(plan: dict[str, Any]) -> dict[str, Any]:
    selectors: dict[str, Any] = {}
    for task in plan.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if str(task.get("kind") or "").lower() != "tool":
            continue
        if str(task.get("tool") or task.get("tool_name") or "") != "manage_company_calendar":
            continue
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        if str(task.get("action") or tool_input.get("action") or "").lower() != "query":
            continue
        for key in ("event_type", "department"):
            if tool_input.get(key) not in (None, "", [], {}):
                selectors.setdefault(key, tool_input.get(key))
    return selectors


def _check_calendar_update_completion(state: dict[str, Any], goal: dict[str, Any]) -> CompletionCheckResult:
    expected = _clean_expected_result(goal.get("expected_result"))
    updates = _calendar_update_results(state)
    if updates:
        successful = [item for item in updates if _calendar_update_success(item)]
        if successful:
            for result in reversed(successful):
                event = _calendar_event_from_result(result)
                mismatches = _calendar_expected_mismatches(expected, event)
                if not mismatches:
                    return CompletionCheckResult(
                        "completed",
                        "calendar_update",
                        "updated_fields_match",
                        expected,
                        {"event": event, "task_id": result.get("task_id")},
                    )
            return CompletionCheckResult(
                "failed",
                "calendar_update",
                "updated_field_mismatch",
                expected,
                {"mismatches": _calendar_expected_mismatches(expected, _calendar_event_from_result(successful[-1]))},
            )
        return CompletionCheckResult("failed", "calendar_update", "update_failed", expected, {"updates": updates[-3:]})

    query_events, query_result = _latest_calendar_query_result(state)
    if query_result:
        if not query_events:
            return CompletionCheckResult("failed", "calendar_update", "not_found", expected, {"event_count": 0, "query_task_id": query_result.get("task_id")})
        if len(query_events) > 1:
            return CompletionCheckResult(
                "needs_clarification",
                "calendar_update",
                "multiple_candidates",
                expected,
                {"event_count": len(query_events), "candidate_events": _compact_events(query_events)},
            )
        if not expected:
            return CompletionCheckResult("needs_clarification", "calendar_update", "missing_expected_result", expected, {"event_count": 1})
        event_id = str(query_events[0].get("event_id") or "").strip()
        if is_unresolved_calendar_event_id(event_id):
            return CompletionCheckResult("failed", "calendar_update", "query_result_missing_event_id", expected, {"event": query_events[0]})
        task = _build_safe_calendar_update_task(event_id=event_id, expected=expected, source="query_result")
        return CompletionCheckResult(
            "incomplete",
            "calendar_update",
            "query_completed_but_update_missing",
            expected,
            {"event_count": 1, "event_id": event_id, "query_task_id": query_result.get("task_id")},
            safe_next_action={"source": "deterministic", "reason": "unique_calendar_event_from_query", "task": task},
        )

    event_id = _single_previous_calendar_event_id(state.get("previous_tool_context") if isinstance(state.get("previous_tool_context"), dict) else {})
    if event_id and expected:
        task = _build_safe_calendar_update_task(event_id=event_id, expected=expected, source="previous_tool_context")
        return CompletionCheckResult(
            "incomplete",
            "calendar_update",
            "previous_context_event_update_missing",
            expected,
            {"event_id": event_id},
            safe_next_action={"source": "deterministic", "reason": "unique_previous_calendar_event", "task": task},
        )
    return CompletionCheckResult("incomplete", "calendar_update", "no_update_result", expected, {})


def _check_skill_completion(state: dict[str, Any], goal: dict[str, Any]) -> CompletionCheckResult:
    target = goal.get("target") if isinstance(goal.get("target"), dict) else {}
    wanted_skill = str(target.get("skill_name") or "").strip()
    for result in reversed(state.get("task_results") or []):
        if not isinstance(result, dict) or result.get("tool_name") != "skill":
            continue
        skill_result = result.get("skill_result") if isinstance(result.get("skill_result"), dict) else {}
        skill_name = str(result.get("skill_name") or skill_result.get("skill_name") or "").strip()
        if wanted_skill and skill_name != wanted_skill:
            continue
        if skill_result.get("ok") is True:
            return CompletionCheckResult("completed", "skill_analysis", "skill_ok", {}, {"skill_name": skill_name})
    return CompletionCheckResult("incomplete", "skill_analysis", "skill_result_missing", {}, {})


def _check_rag_completion(state: dict[str, Any], goal: dict[str, Any]) -> CompletionCheckResult:
    del goal
    rag_results = [item for item in (state.get("task_results") or []) if isinstance(item, dict) and str(item.get("kind") or "").lower() == "rag"]
    if not rag_results:
        return CompletionCheckResult("incomplete", "rag_answer", "rag_result_missing", {}, {})
    supported = [
        item
        for item in rag_results
        if item.get("sources") or item.get("supporting_sources") or str(item.get("status") or "").lower() == "ok"
    ]
    related = [item for item in rag_results if item.get("related_sources")]
    if supported and len(supported) == len(rag_results):
        return CompletionCheckResult("completed", "rag_answer", "supporting_sources_present", {}, {"supported_count": len(supported)})
    if supported or related:
        return CompletionCheckResult("partial", "rag_answer", "partial_or_related_evidence", {}, {"supported_count": len(supported), "related_count": len(related)})
    return CompletionCheckResult("failed", "rag_answer", "unsupported", {}, {"rag_result_count": len(rag_results)})


def _check_tool_query_completion(state: dict[str, Any], goal: dict[str, Any]) -> CompletionCheckResult:
    target = goal.get("target") if isinstance(goal.get("target"), dict) else {}
    wanted_tool = str(target.get("tool_name") or "").strip()
    wanted_action = str(target.get("action") or "").strip()
    for result in reversed(state.get("task_results") or []):
        if not isinstance(result, dict) or str(result.get("kind") or "").lower() != "tool":
            continue
        if wanted_tool and result.get("tool_name") != wanted_tool:
            continue
        if wanted_action and result.get("action") != wanted_action:
            continue
        if str(result.get("status") or "").lower() in {"ok", "success"}:
            return CompletionCheckResult("completed", "tool_query", "tool_result_present", {}, {"task_id": result.get("task_id")})
    return CompletionCheckResult("incomplete", "tool_query", "tool_result_missing", {}, {})


def _calendar_update_results(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in (state.get("task_results") or [])
        if isinstance(item, dict)
        and item.get("tool_name") == "manage_company_calendar"
        and str(item.get("action") or "").lower() == "update"
    ]


def _calendar_update_success(result: dict[str, Any]) -> bool:
    tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
    event = tool_result.get("event") if isinstance(tool_result.get("event"), dict) else {}
    event_id = event.get("event_id") or tool_result.get("event_id")
    return str(tool_result.get("status") or "").lower() == "updated" and not is_unresolved_calendar_event_id(event_id)


def _calendar_event_from_result(result: dict[str, Any]) -> dict[str, Any]:
    tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
    return dict(tool_result.get("event") or {}) if isinstance(tool_result.get("event"), dict) else {}


def _calendar_expected_mismatches(expected: dict[str, Any], event: dict[str, Any]) -> list[dict[str, str]]:
    mismatches: list[dict[str, str]] = []
    for field, value in expected.items():
        if field == "date_expression":
            continue
        expected_text = str(value or "")
        actual_text = str(event.get(field) or "")
        if expected_text != actual_text:
            mismatches.append({"field": field, "expected": expected_text, "actual": actual_text})
    return mismatches


def _latest_calendar_query_result(state: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    for result in reversed(state.get("task_results") or []):
        if not isinstance(result, dict):
            continue
        if result.get("tool_name") != "manage_company_calendar" or str(result.get("action") or "").lower() != "query":
            continue
        tool_result = result.get("tool_result") if isinstance(result.get("tool_result"), dict) else {}
        events = [event for event in (tool_result.get("events") or []) if isinstance(event, dict)]
        return events, result
    return [], {}


def _build_safe_calendar_update_task(*, event_id: str, expected: dict[str, Any], source: str) -> dict[str, Any]:
    tool_input = {
        field: value
        for field, value in expected.items()
        if field in CALENDAR_EXPECTED_UPDATE_FIELDS and value not in (None, "", [], {})
    }
    tool_input["action"] = "update"
    tool_input["event_id"] = event_id
    return {
        "task_id": "goal_react_calendar_update",
        "kind": "tool",
        "objective": "根据 goal_contract 补执行缺失的日程更新",
        "tool": "manage_company_calendar",
        "tool_name": "manage_company_calendar",
        "action": "update",
        "tool_input": tool_input,
        "depends_on": [],
        "_safe_next_action_source": source,
    }


def _single_previous_calendar_event_id(previous: dict[str, Any]) -> str:
    if not previous:
        return ""
    if previous.get("domain") != "calendar" and previous.get("tool_name") != "manage_company_calendar":
        return ""
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


def _compact_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for event in events[:10]:
        compact.append(
            {
                key: event.get(key)
                for key in ("event_id", "date", "weekday_zh", "time", "title", "location", "type", "department")
                if event.get(key) not in (None, "", [], {})
            }
        )
    return compact


__all__ = [
    "CompletionCheckResult",
    "check_goal_completion",
    "derive_goal_contract_from_plan",
    "normalize_goal_contract",
    "resolve_goal_contract_time",
]
