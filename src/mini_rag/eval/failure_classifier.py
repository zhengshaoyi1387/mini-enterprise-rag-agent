from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


FailureCategory = Literal[
    "passed",
    "planning_error",
    "time_resolution_error",
    "tool_input_error",
    "tool_execution_error",
    "rag_retrieval_error",
    "rag_evidence_error",
    "answer_synthesis_error",
    "safety_error",
    "memory_context_error",
    "infra_error",
    "evaluator_error",
]


INFRA_PATTERNS = (
    "quota",
    "403",
    "forbidden",
    "invalid api key",
    "invalid_api_key",
    "unauthorized",
    "authentication",
    "network",
    "timeout",
    "timed out",
    "connection refused",
    "connection error",
    "name resolution",
)

PLACEHOLDER_EVENT_IDS = ("all", "multiple", "event_id_from", "event_id_from_x", "*")


@dataclass(frozen=True)
class FailureClassification:
    case_id: str = ""
    passed: bool = False
    failure_category: FailureCategory = "passed"
    failure_categories: tuple[FailureCategory, ...] = field(default_factory=tuple)
    reason: str = ""
    node_hint: str = ""
    fix_hint: str = ""
    question: str = ""
    expected_brief: str = ""
    actual_brief: str = ""
    trace_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "failure_category": self.failure_category,
            "failure_categories": list(self.failure_categories or (() if self.failure_category == "passed" else (self.failure_category,))),
            "reason": self.reason,
            "node_hint": self.node_hint,
            "fix_hint": self.fix_hint,
            "question": self.question,
            "expected_brief": self.expected_brief,
            "actual_brief": self.actual_brief,
            "trace_path": self.trace_path,
        }


def _text(value: Any) -> str:
    return str(value or "")


def _lower_blob(*values: Any) -> str:
    return "\n".join(_text(value) for value in values).lower()


def _compact(value: Any, limit: int = 220) -> str:
    text = _text(value).replace("\n", " ").strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _has_infra_error(error: Any) -> bool:
    text = _lower_blob(error)
    return any(pattern in text for pattern in INFRA_PATTERNS)


def _event_id_is_unsafe(value: Any) -> bool:
    text = _text(value).strip().lower()
    return bool(text) and (text in PLACEHOLDER_EVENT_IDS or text.startswith("event_id_from"))


def _candidate_has_relevant_source(question: str, candidates: list[dict[str, Any]]) -> bool:
    del question
    return any(isinstance(src, dict) for src in candidates)


def _extract_candidates(trace: dict[str, Any], task_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [src for src in (trace.get("candidate_sources") or []) if isinstance(src, dict)]
    for result in task_results:
        if isinstance(result, dict):
            candidates.extend(src for src in (result.get("candidate_sources") or []) if isinstance(src, dict))
    return candidates


def _extract_sources(trace: dict[str, Any], sources: list[dict[str, Any]], task_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = [src for src in sources if isinstance(src, dict)]
    output.extend(src for src in (trace.get("sources") or []) if isinstance(src, dict))
    for result in task_results:
        if isinstance(result, dict):
            output.extend(src for src in (result.get("sources") or []) if isinstance(src, dict))
    return output


def classify_failure(
    *,
    case_id: str,
    question: str,
    expected: dict[str, Any] | None,
    actual_answer: str,
    trace: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    task_results: list[dict[str, Any]],
    execution_plan: dict[str, Any],
    sources: list[dict[str, Any]],
    error: Any = None,
) -> FailureClassification:
    expected = expected if isinstance(expected, dict) else {}
    if _has_infra_error(error):
        return FailureClassification(
            case_id=case_id,
            passed=False,
            failure_category="infra_error",
            failure_categories=("infra_error",),
            reason=f"External model/dependency failure: {_compact(error)}",
            node_hint="runtime/external dependency",
            fix_hint="Do not count quota/auth/network failures as Agent logic failures.",
            question=question,
            expected_brief=_compact(expected),
            actual_brief=_compact(actual_answer or error),
        )

    for call in tool_calls:
        args = call.get("args") if isinstance(call, dict) and isinstance(call.get("args"), dict) else {}
        if _event_id_is_unsafe(args.get("event_id")):
            return FailureClassification(
                case_id=case_id,
                passed=False,
                failure_category="safety_error",
                failure_categories=("safety_error",),
                reason="Unsafe placeholder event_id reached a real calendar write path.",
                node_hint="capabilities/calendar/validator.py",
                fix_hint="Block event_id=all/multiple/event_id_from before ToolExecutor.",
                question=question,
                expected_brief=_compact(expected),
                actual_brief=_compact(actual_answer),
            )

    resolved_facts = trace.get("resolved_time_facts") or []
    if any(isinstance(item, dict) and str(item.get("kind") or "") == "none" for item in resolved_facts):
        return FailureClassification(
            case_id=case_id,
            passed=False,
            failure_category="time_resolution_error",
            failure_categories=("time_resolution_error",),
            reason="Plan contains a time expression but TimeResolver returned kind=none.",
            node_hint="capabilities/datetime/resolver.py",
            fix_hint="Add deterministic support in the unified TimeResolver, not in prompts.",
            question=question,
            expected_brief=_compact(expected),
            actual_brief=_compact(actual_answer),
        )

    tasks = [task for task in (execution_plan.get("tasks") or []) if isinstance(task, dict)]
    if not tasks and (expected.get("expected_tool") or expected.get("expected_tools") or expected.get("requires_rag")):
        return FailureClassification(
            case_id=case_id,
            passed=False,
            failure_category="planning_error",
            failure_categories=("planning_error",),
            reason="Planner did not produce required tool/RAG tasks.",
            node_hint="orchestration/agentic_nodes.py::plan_with_llm",
            fix_hint="Inspect Planner schema/prompt and normalized execution_plan.",
            question=question,
            expected_brief=_compact(expected),
            actual_brief=_compact(actual_answer),
        )

    for task in tasks:
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        action = _text(task.get("action") or tool_input.get("action")).lower()
        if action in {"create", "update", "delete"}:
            if any(_event_id_is_unsafe(tool_input.get("event_id")) for _ in (0,)):
                category: FailureCategory = "safety_error"
                return FailureClassification(
                    case_id=case_id,
                    passed=False,
                    failure_category=category,
                    failure_categories=(category,),
                    reason="Unsafe placeholder event_id remained in execution_plan.",
                    node_hint="planning/gates.py",
                    fix_hint="Validate selector/event_id before write execution.",
                    question=question,
                    expected_brief=_compact(expected),
                    actual_brief=_compact(actual_answer),
                )
            if action == "create" and not all(tool_input.get(key) for key in ("date", "time", "title")):
                return FailureClassification(
                    case_id=case_id,
                    passed=False,
                    failure_category="tool_input_error",
                    failure_categories=("tool_input_error",),
                    reason="Calendar create task lacks required concrete slots.",
                    node_hint="execution/tool_input.py",
                    fix_hint="Keep missing-slot create tasks in clarification_tasks.",
                    question=question,
                    expected_brief=_compact(expected),
                    actual_brief=_compact(actual_answer),
                )

    if any(isinstance(result, dict) and str(result.get("status") or "") in {"error", "failed"} for result in task_results):
        return FailureClassification(
            case_id=case_id,
            passed=False,
            failure_category="tool_execution_error",
            failure_categories=("tool_execution_error",),
            reason="A task_result reports tool execution failure.",
            node_hint="execution/tool_executor.py",
            fix_hint="Inspect tool result status and payload.",
            question=question,
            expected_brief=_compact(expected),
            actual_brief=_compact(actual_answer),
        )

    rag_results = [result for result in task_results if isinstance(result, dict) and str(result.get("kind") or "").lower() == "rag"]
    all_sources = _extract_sources(trace, sources, task_results)
    candidates = _extract_candidates(trace, task_results)
    if rag_results and not all_sources:
        if _candidate_has_relevant_source(question, candidates):
            return FailureClassification(
                case_id=case_id,
                passed=False,
                failure_category="rag_evidence_error",
                failure_categories=("rag_evidence_error",),
                reason="Relevant candidate evidence was retrieved but did not become supporting evidence.",
                node_hint="capabilities/rag/evidence_judge.py",
                fix_hint="Check LLM Evidence Judge and RAG answerability gate.",
                question=question,
                expected_brief=_compact(expected),
                actual_brief=_compact(actual_answer),
            )
        return FailureClassification(
            case_id=case_id,
            passed=False,
            failure_category="rag_retrieval_error",
            failure_categories=("rag_retrieval_error",),
            reason="No supporting or candidate RAG source was retrieved.",
            node_hint="capabilities/rag/service.py",
            fix_hint="Inspect retrieval_query, KB routing, and retriever configuration.",
            question=question,
            expected_brief=_compact(expected),
            actual_brief=_compact(actual_answer),
        )

    if not _text(actual_answer).strip() and (
        any(isinstance(result, dict) and str(result.get("status") or "") in {"ok", "success"} for result in task_results) or all_sources
    ):
        return FailureClassification(
            case_id=case_id,
            passed=False,
            failure_category="answer_synthesis_error",
            failure_categories=("answer_synthesis_error",),
            reason="Execution produced usable facts but final answer was empty or missing.",
            node_hint="answer/service.py",
            fix_hint="Inspect AnswerPacket construction and Answer LLM prompt.",
            question=question,
            expected_brief=_compact(expected),
            actual_brief=_compact(actual_answer),
        )

    return FailureClassification(
        case_id=case_id,
        passed=False,
        failure_category="answer_synthesis_error",
        failure_categories=("answer_synthesis_error",),
        reason="Default attribution: final answer did not satisfy expected checks.",
        node_hint="answer/service.py",
        fix_hint="Inspect compact AnswerPacket facts against final answer.",
        question=question,
        expected_brief=_compact(expected),
        actual_brief=_compact(actual_answer),
    )


__all__ = ["FailureCategory", "FailureClassification", "classify_failure"]
