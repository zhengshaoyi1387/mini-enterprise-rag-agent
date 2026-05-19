from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from mini_rag.capabilities.verifier import task_result_quality_issues, terminal_tool_results_require_answer
from mini_rag.graph.prompts import COMPLETION_REFLECT_SYSTEM, REFLECT_EVIDENCE_SYSTEM, format_completion_reflect_user, format_reflect_user
from mini_rag.graph.utils import coerce_list, compact_evidence_text, dedupe_keep_order
from mini_rag.planning.coverage_checker import check_goal_coverage
from mini_rag.planning.goal_extractor import Goal, extract_goals

InvokeJson = Callable[..., dict[str, Any]]
NormalizeTask = Callable[[Any, int, dict[str, Any] | None], dict[str, Any]]
NormalizeQueryKey = Callable[[str], str]
PrimeNextTask = Callable[[dict[str, Any]], dict[str, Any] | None]
ResolveTasks = Callable[[dict[str, Any]], bool]


class CompletionReflectionService:
    """Coverage-aware completion reflection outside orchestration nodes."""

    def __init__(
        self,
        *,
        settings: Any,
        invoke_json: InvokeJson,
        normalize_execution_task: NormalizeTask,
        normalize_query_key: NormalizeQueryKey,
        prime_next_task: PrimeNextTask,
        resolve_calendar_update_tasks: ResolveTasks,
        resolve_calendar_delete_tasks: ResolveTasks,
    ) -> None:
        self.settings = settings
        self._invoke_json = invoke_json
        self._normalize_execution_task = normalize_execution_task
        self._normalize_query_key = normalize_query_key
        self._prime_next_task = prime_next_task
        self._resolve_calendar_update_tasks = resolve_calendar_update_tasks
        self._resolve_calendar_delete_tasks = resolve_calendar_delete_tasks

    @staticmethod
    def _plan_tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            task
            for task in ((state.get("execution_plan") or {}).get("tasks") or [])
            if isinstance(task, dict) and str(task.get("kind") or "") in {"rag", "tool"}
        ]

    def _store_goal_coverage(self, state: dict[str, Any], goals: tuple[Goal, ...]) -> Any:
        report = check_goal_coverage(
            goals,
            execution_plan=state.get("execution_plan") or {},
            task_results=[r for r in (state.get("task_results") or []) if isinstance(r, dict)],
            rag_results=[],
        )
        state["goals"] = [asdict(goal) for goal in goals]
        state["goal_coverage"] = asdict(report)
        return report

    def reflect(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("route") in {"reject", "direct"} and not state.get("task_results"):
            state["completion_assessment"] = {
                "ready_to_answer": True,
                "completed_objectives": [],
                "missing_objectives": [],
                "unsupported_parts": [],
                "next_action": "answer",
                "reason": "direct route",
            }
            return state

        self._resolve_calendar_update_tasks(state)
        self._resolve_calendar_delete_tasks(state)
        next_planned_task = self._prime_next_task(state)
        if next_planned_task:
            state["completion_assessment"] = {
                "ready_to_answer": False,
                "completed_objectives": [str(x) for x in state.get("completed_tasks", [])],
                "missing_objectives": [str(next_planned_task.get("objective") or next_planned_task.get("task_id") or "")],
                "unsupported_parts": [],
                "next_action": "continue",
                "followup_tasks": [next_planned_task],
                "reason": "planned task remains",
            }
            state.setdefault("observations", []).append({"type": "completion_reflection", **state["completion_assessment"]})
            return state

        plan_tasks = self._plan_tasks(state)
        goals = extract_goals(
            str(state.get("question") or ""),
            {
                "standalone_query": state.get("standalone_query"),
                "knowledge_requirement": state.get("knowledge_requirement") or {},
            },
            state.get("execution_plan") or {},
        )
        coverage = self._store_goal_coverage(state, goals)
        has_rag_result = any(
            isinstance(result, dict) and str(result.get("kind") or "").lower() == "rag"
            for result in (state.get("task_results") or [])
        )
        if goals and not coverage.ready_to_answer and coverage.should_use_rag and not has_rag_result:
            state["completion_assessment"] = {
                "ready_to_answer": False,
                "completed_objectives": list(coverage.covered_goal_ids),
                "missing_objectives": list(coverage.missing_goal_ids),
                "unsupported_parts": list(coverage.unsupported_goal_ids),
                "next_action": "continue",
                "followup_tasks": [],
                "reason": coverage.reason,
            }
            state.setdefault("observations", []).append({"type": "completion_reflection", **state["completion_assessment"]})
            return state

        completed = {str(x) for x in state.get("completed_tasks", [])}
        planned_ids = {str(task.get("task_id") or "") for task in plan_tasks if task.get("task_id")}
        task_results = [r for r in (state.get("task_results") or []) if isinstance(r, dict)]
        structural_errors = task_result_quality_issues(plan_tasks, task_results)

        if structural_errors and terminal_tool_results_require_answer(structural_errors):
            state["completion_assessment"] = {
                "ready_to_answer": True,
                "completed_objectives": [
                    str(result.get("objective") or result.get("task_id") or "")
                    for result in task_results
                    if str(result.get("status") or "").lower() not in {"needs_clarification", "blocked"}
                ],
                "missing_objectives": [
                    str(
                        result.get("result_summary")
                        or (
                            result.get("tool_result").get("message")
                            if isinstance(result.get("tool_result"), dict)
                            else ""
                        )
                        or result.get("objective")
                        or ""
                    )
                    for result in structural_errors
                ],
                "unsupported_parts": [],
                "next_action": "answer",
                "followup_tasks": [],
                "reason": "terminal tool status requires user-facing answer",
            }
            state.setdefault("observations", []).append({"type": "completion_reflection", **state["completion_assessment"]})
            return state

        if plan_tasks and planned_ids.issubset(completed) and not structural_errors:
            state["completion_assessment"] = {
                "ready_to_answer": True,
                "completed_objectives": [str(task.get("objective") or task.get("task_id") or "") for task in plan_tasks],
                "missing_objectives": [],
                "unsupported_parts": [
                    str(r.get("objective") or r.get("query") or "")
                    for r in task_results
                    if str(r.get("status") or "").lower() in {"empty", "no_evidence"}
                ],
                "next_action": "answer",
                "followup_tasks": [],
                "reason": "all planned goals covered",
            }
            state.setdefault("observations", []).append({"type": "completion_reflection", **state["completion_assessment"]})
            return state

        completion_round = int(state.get("completion_reflect_round") or 0) + 1
        state["completion_reflect_round"] = completion_round
        evidence_text = state.get("supporting_evidence_brief") or state.get("evidence_brief") or compact_evidence_text(
            state.get("retrieved_docs", []), entities=state.get("entities", [])
        )
        payload = self._invoke_json(
            state=state,
            node="completion_reflect",
            system=COMPLETION_REFLECT_SYSTEM,
            user=format_completion_reflect_user(
                question=state.get("question", ""),
                execution_plan=state.get("execution_plan", {}),
                task_results=state.get("task_results", []),
                evidence_text=evidence_text,
                sources=state.get("sources", []),
                completion_round=completion_round,
            ),
            default={
                "ready_to_answer": True,
                "completed_objectives": [],
                "missing_objectives": [],
                "unsupported_parts": [],
                "next_action": "answer",
                "followup_tasks": [],
                "reason": "completion reflection fallback",
            },
        )
        followups = [
            self._normalize_execution_task(task, idx, state.get("raw_plan", {}))
            for idx, task in enumerate(coerce_list(payload.get("followup_tasks")))
            if isinstance(task, dict)
        ]
        completed = set(str(x) for x in (state.get("completed_tasks") or []))
        executed_keys = set(str(x) for x in (state.get("_executed_query_keys") or []))

        def keep_followup(task: dict[str, Any]) -> bool:
            task_id = str(task.get("task_id") or "")
            query = str(task.get("query") or (task.get("tool_input") or {}).get("query") or "").strip()
            if task_id and task_id in completed:
                return False
            if query and self._normalize_query_key(query) in executed_keys:
                return False
            return bool(task.get("kind"))

        original_followup_count = len(followups)
        followups = [task for task in followups if keep_followup(task)]
        max_replans = max(0, int(getattr(self.settings, "agent_completion_max_replans", 2) or 0))
        ready = bool(payload.get("ready_to_answer"))
        next_action = str(payload.get("next_action") or "answer").lower()

        if completion_round > max_replans:
            ready = True
            next_action = "answer"
            followups = []
        elif not ready and next_action in {"continue", "replan"} and followups:
            state["task_queue"] = list(state.get("task_queue") or []) + followups
            self._resolve_calendar_update_tasks(state)
            self._resolve_calendar_delete_tasks(state)
            self._prime_next_task(state)
        else:
            if original_followup_count and not followups:
                state.setdefault("observations", []).append({"type": "duplicate_followup_guard", "remaining_followup_count": 0})
            followups = []
            if not ready:
                ready = True
                next_action = "answer"

        state["completion_assessment"] = {
            "ready_to_answer": ready,
            "completed_objectives": [str(x) for x in coerce_list(payload.get("completed_objectives"))],
            "missing_objectives": [str(x) for x in coerce_list(payload.get("missing_objectives"))],
            "unsupported_parts": [str(x) for x in coerce_list(payload.get("unsupported_parts"))],
            "next_action": next_action,
            "followup_tasks": followups,
            "reason": str(payload.get("reason") or ""),
        }
        state.setdefault("observations", []).append({"type": "completion_reflection", **state["completion_assessment"]})
        return state


class EvidenceReflectionService:
    """LLM-assisted RAG evidence reflection with deterministic loop bounds."""

    def __init__(
        self,
        *,
        settings: Any,
        invoke_json: InvokeJson,
        normalize_query_key: NormalizeQueryKey,
    ) -> None:
        self.settings = settings
        self._invoke_json = invoke_json
        self._normalize_query_key = normalize_query_key

    @staticmethod
    def normalize_tasks(value: Any, fallback_query: str) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for item in coerce_list(value):
            if isinstance(item, str):
                item = {"query": item, "purpose": "search", "target_entity": None}
            if not isinstance(item, dict):
                continue
            query = str(item.get("query") or "").strip()
            if not query:
                continue
            task = {
                "query": query,
                "purpose": str(item.get("purpose") or "search"),
                "target_entity": item.get("target_entity"),
            }
            for opt_key in ("top_k", "candidate_k", "enable_rerank"):
                if opt_key in item:
                    task[opt_key] = item.get(opt_key)
            tasks.append(task)
        if not tasks and fallback_query:
            tasks = [{"query": fallback_query, "purpose": "answer_question", "target_entity": None}]
        return dedupe_keep_order(tasks, key=lambda task: str(task.get("query")))

    def reflect_evidence(self, state: dict[str, Any]) -> dict[str, Any]:
        reflect_round = int(state.get("reflect_round") or 0) + 1
        state["reflect_round"] = reflect_round
        evidence_text = state.get("evidence_brief") or compact_evidence_text(state.get("retrieved_docs", []), entities=state.get("entities", []))
        payload = self._invoke_json(
            state=state,
            node="reflect_evidence",
            system=REFLECT_EVIDENCE_SYSTEM,
            user=format_reflect_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                executed_queries=state.get("executed_queries", []),
                evidence_text=evidence_text,
            ),
            default={
                "is_sufficient": bool(state.get("retrieved_docs")),
                "can_answer_partial": bool(state.get("retrieved_docs")),
                "should_continue_retrieval": False,
                "missing_information": [],
                "followup_tasks": [],
                "stop_reason": "证据反思解析失败，基于现有证据进入回答。",
                "reason": "证据反思解析失败，基于现有证据进入回答。",
            },
        )
        followup_tasks = self.normalize_tasks(payload.get("followup_tasks"), fallback_query="")
        if not followup_tasks and payload.get("followup_queries") is not None:
            followup_tasks = self.normalize_tasks(payload.get("followup_queries"), fallback_query="")
        executed = set(state.get("executed_queries", []))
        executed_keys = set(state.get("_executed_query_keys", []))
        followup_tasks = [
            task
            for task in followup_tasks
            if str(task.get("query", "")).strip() not in executed
            and self._normalize_query_key(str(task.get("query", ""))) not in executed_keys
        ]
        max_followups = max(0, int(getattr(self.settings, "agent_max_followup_tasks", 2) or 0))
        followup_tasks = followup_tasks[:max_followups]
        can_answer_partial = bool(payload.get("can_answer_partial"))
        is_sufficient = bool(payload.get("is_sufficient"))
        should_continue = bool(payload.get("should_continue_retrieval"))
        if "should_continue_retrieval" not in payload:
            should_continue = bool(followup_tasks) and not is_sufficient
        stop_reason = str(payload.get("stop_reason") or "")
        if is_sufficient or not should_continue:
            followup_tasks = []
            stop_reason = stop_reason or ("evidence_sufficient" if is_sufficient else "llm_decided_no_more_retrieval")
        if reflect_round >= max(1, int(getattr(self.settings, "agent_reflect_max_rounds", 1) or 1)):
            followup_tasks = []
            stop_reason = stop_reason or "max_reflection_rounds_reached"
        state["evidence_assessment"] = {
            "is_sufficient": is_sufficient,
            "can_answer_partial": can_answer_partial,
            "should_continue_retrieval": should_continue,
            "missing_information": [str(x) for x in coerce_list(payload.get("missing_information"))],
            "followup_tasks": followup_tasks,
            "reason": str(payload.get("reason") or ""),
        }
        if stop_reason:
            state["evidence_assessment"]["stop_reason"] = stop_reason
        state["pending_search_tasks"] = followup_tasks
        state.setdefault("observations", []).append({"type": "evidence_reflection", **state["evidence_assessment"]})
        return state
