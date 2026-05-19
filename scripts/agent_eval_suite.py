from __future__ import annotations

"""Unified evaluation runner for RAG, tools, and end-to-end Agent behavior.

This script is intentionally a single, dependency-light file. It reuses the
project's current Agent/RAG entry points, reads the existing trace shape, and
adds transparent rule-based checks plus optional LLM-as-judge scoring.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from mini_rag.config import Settings, get_settings  # noqa: E402
from mini_rag.eval.failure_classifier import classify_failure  # noqa: E402
from mini_rag.eval.run_report import write_eval_report as write_auto_eval_report  # noqa: E402
from mini_rag.evaluation.metrics import citation_hit, refusal_hit, source_hit  # noqa: E402
from mini_rag.models.qwen import build_qwen_chat_model  # noqa: E402
from mini_rag.utils import dump_json, ensure_dir  # noqa: E402


SUITE_CHOICES = ("rag", "tool", "e2e", "all")
JUDGE_CHOICES = ("rule", "llm", "both")
MODE_CHOICES = ("vector", "hybrid", "hybrid_rerank")
DEFAULT_EVAL_FIXED_NOW = "2026-05-17 01:00:00 Asia/Shanghai"
WRITE_ACTIONS = {"create", "update", "delete"}
REFUSAL_MARKERS = (
    "拒绝",
    "无法回答",
    "无法确定",
    "无法提供",
    "不能执行",
    "不能提供",
    "证据不足",
    "权限不足",
    "not allowed",
    "not enough evidence",
    "cannot answer",
    "refuse",
    "不会执行",
)
REFUSAL_PATTERNS = (
    r"没有找到[^。；;\n]*(?:信息|证据|依据)",
    r"未找到[^。；;\n]*(?:信息|证据|依据)",
    r"没有直接提到",
    r"无法(?:直接|根据当前知识库)?回答",
    r"无法根据当前知识库",
    r"当前知识库[^。；;\n]*(?:没有|未)[^。；;\n]*(?:信息|证据|依据)",
    r"(?:你|您|当前角色|当前账号|普通员工|员工)[^。；;\n]*(?:没有权限|无权|权限不足)[^。；;\n]*(?:使用|执行|访问|查看|查询|修改|删除|更新|创建|新增)",
    r"无权执行",
)
NOISY_SOURCE_NAMES = {
    "README.md",
    "README_USE.md",
    "MANIFEST.json",
    "DOCUMENT_MANIFEST.json",
    "RAG_EVAL_SEED_QUESTIONS.md",
}


@dataclass
class EvalCaseResult:
    suite: str
    id: str
    question: str
    role: str
    passed: bool
    latency_ms: float = 0.0
    rule_scores: dict[str, Any] = field(default_factory=dict)
    llm_scores: dict[str, Any] = field(default_factory=dict)
    retrieved_sources: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    task_results: list[dict[str, Any]] = field(default_factory=list)
    answer_preview: str = ""
    failure_reasons: list[str] = field(default_factory=list)
    error: str | None = None
    route: str | None = None
    trace_id: str | None = None
    warnings: list[str] = field(default_factory=list)
    plan_with_llm: dict[str, Any] = field(default_factory=dict)
    react_execute: dict[str, Any] = field(default_factory=dict)
    execution_plan: dict[str, Any] = field(default_factory=dict)
    actual_success: bool | None = None
    infra_error: bool = False
    error_type: str | None = None
    failure_category: str = ""
    raw_case: dict[str, Any] = field(default_factory=dict)

    def to_report_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite,
            "id": self.id,
            "question": self.question,
            "role": self.role,
            "passed": self.passed,
            "latency_ms": self.latency_ms,
            "route": self.route,
            "trace_id": self.trace_id,
            "rule_scores": self.rule_scores,
            "llm_scores": self.llm_scores,
            "retrieved_sources": self.retrieved_sources,
            "tool_calls": self.tool_calls,
            "task_results": compact_task_results(self.task_results),
            "execution_plan": self.execution_plan,
            "actual_success": self.actual_success,
            "infra_error": self.infra_error,
            "error_type": self.error_type,
            "failure_category": self.failure_category,
            "plan_with_llm": self.plan_with_llm,
            "react_execute": self.react_execute,
            "answer_preview": self.answer_preview,
            "failure_reasons": self.failure_reasons,
            "warnings": self.warnings,
            "error": self.error,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified RAG/tool/e2e evaluation suite with rule and LLM-as-judge modes."
    )
    parser.add_argument("--suite", choices=SUITE_CHOICES, required=True)
    parser.add_argument("--judge", choices=JUDGE_CHOICES, default="rule")
    parser.add_argument("--mode", choices=MODE_CHOICES, default="hybrid")
    parser.add_argument("--questions", default=None, help="Question JSONL for rag/tool/e2e when suite is not all.")
    parser.add_argument("--rag-questions", default=None)
    parser.add_argument("--tool-questions", default=None)
    parser.add_argument("--e2e-questions", default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--candidate-k", type=int, default=None)
    parser.add_argument("--role", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case-id", default=None)
    parser.add_argument("--output", required=True, help="Output prefix without suffix.")
    parser.add_argument("--fixed-now", default=DEFAULT_EVAL_FIXED_NOW, help="Fixed eval clock for relative-date cases.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--llm-judge-model", default=None)
    parser.add_argument("--judge-sample-rate", type=float, default=0.0)
    parser.add_argument("--judge-failed-only", dest="judge_failed_only", action="store_true", default=True)
    parser.add_argument("--judge-all", dest="judge_failed_only", action="store_false")
    parser.add_argument("--stop-on-infra-error", dest="stop_on_infra_error", action="store_true", default=True)
    parser.add_argument("--no-stop-on-infra-error", dest="stop_on_infra_error", action="store_false")
    parser.add_argument(
        "--restore-fixtures",
        dest="no_restore_fixtures",
        action="store_false",
        help="Restore calendar/attendance base fixtures before isolated tool/e2e cases.",
    )
    parser.add_argument(
        "--no-restore-fixtures",
        dest="no_restore_fixtures",
        action="store_true",
        help="Do not restore calendar/attendance base fixtures before isolated tool/e2e cases.",
    )
    parser.set_defaults(no_restore_fixtures=False, judge_failed_only=True, stop_on_infra_error=True)
    return parser.parse_args()


def load_jsonl(path: str | Path | None, *, limit: int | None = None, case_id: str | None = None) -> list[dict[str, Any]]:
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        print(f"[warn] question file not found: {file_path}")
        return []
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"[warn] skip invalid jsonl line {line_number}: {exc}")
            continue
        item.setdefault("id", item.get("case_id") or f"case_{line_number:03d}")
        if case_id and str(item.get("id") or item.get("case_id")) != str(case_id):
            continue
        cases.append(item)
        if limit is not None and len(cases) >= limit:
            break
    return cases


def resolve_suite_files(args: argparse.Namespace) -> dict[str, str | None]:
    if args.suite == "all":
        return {
            "rag": args.rag_questions,
            "tool": args.tool_questions,
            "e2e": args.e2e_questions,
        }
    return {args.suite: args.questions}


def configure_settings(args: argparse.Namespace) -> Settings:
    if getattr(args, "fixed_now", None):
        os.environ.setdefault("AGENT_EVAL_FIXED_NOW", str(args.fixed_now))
    settings = get_settings()
    if args.top_k is not None:
        settings.top_k = args.top_k
    if args.candidate_k is not None:
        settings.candidate_k = args.candidate_k
    if args.mode == "vector":
        settings.retrieval_mode = "vector"
        settings.rerank_enabled = False
    elif args.mode == "hybrid":
        settings.retrieval_mode = "hybrid"
        settings.rerank_enabled = False
    elif args.mode == "hybrid_rerank":
        settings.retrieval_mode = "hybrid"
        settings.rerank_enabled = True
    return settings


def retrieval_options(mode: str) -> tuple[str, bool]:
    if mode == "vector":
        return "vector", False
    if mode == "hybrid_rerank":
        return "hybrid", True
    return "hybrid", False


def run_rag_case(case: dict[str, Any], settings: Settings, args: argparse.Namespace, runner_cache: dict[str, Any]) -> dict[str, Any]:
    from mini_rag.agent.agent import EnterpriseKnowledgeAgent

    qa = runner_cache.get("agent")
    if qa is None:
        qa = EnterpriseKnowledgeAgent(settings)
        runner_cache["agent"] = qa
    retrieval_mode, enable_rerank = retrieval_options(args.mode)
    case_id = str(case.get("id") or case.get("case_id") or uuid4().hex)
    return qa.ask(
        str(case.get("question") or ""),
        session_id=str(case.get("session_id") or f"eval_rag_{case_id}_{uuid4().hex[:8]}"),
        retrieval_mode=retrieval_mode,
        enable_rerank=enable_rerank,
        user_id=str(case.get("user_id") or "eval_user"),
        role=str(case.get("role") or args.role or "employee"),
        trace_id=str(case.get("trace_id") or f"eval_trace_{uuid4().hex}"),
        kb_ids=case.get("kb_ids"),
        override_now=os.environ.get("AGENT_EVAL_FIXED_NOW"),
    )


def run_agent_case(case: dict[str, Any], settings: Settings, args: argparse.Namespace, runner_cache: dict[str, Any]) -> dict[str, Any]:
    from mini_rag.agent.agent import EnterpriseKnowledgeAgent

    agent = runner_cache.get("agent")
    if agent is None:
        agent = EnterpriseKnowledgeAgent(settings)
        runner_cache["agent"] = agent
    case_id = str(case.get("id") or case.get("case_id") or uuid4().hex)
    role = str(case.get("role") or args.role or "employee")
    session_id = str(case.get("session_id") or f"eval_{case_id}_{uuid4().hex[:8]}")
    trace_id = str(case.get("trace_id") or f"eval_trace_{uuid4().hex}")
    kb_ids = case.get("kb_ids")
    retrieval_mode, enable_rerank = retrieval_options(args.mode)
    return agent.ask(
        str(case.get("question") or ""),
        session_id=session_id,
        retrieval_mode=retrieval_mode,
        enable_rerank=enable_rerank,
        user_id=str(case.get("user_id") or "eval_user"),
        role=role,
        trace_id=trace_id,
        kb_ids=kb_ids if isinstance(kb_ids, list) else None,
    )


def run_case(
    suite: str,
    case: dict[str, Any],
    settings: Settings,
    args: argparse.Namespace,
    runner_cache: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    if suite == "rag":
        result = run_rag_case(case, settings, args, runner_cache)
    else:
        with backup_restore_paths(detect_backup_paths(settings)):
            if should_restore_fixtures(args, case):
                restore_fixture_pairs(detect_fixture_pairs(settings))
            result = run_agent_case(case, settings, args, runner_cache)
            if should_restore_fixtures(args, case):
                restore_fixture_pairs(detect_fixture_pairs(settings))
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return result, latency_ms


def extract_trace(result: dict[str, Any], settings: Settings | None = None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    trace = result.get("trace")
    if isinstance(trace, dict) and trace:
        return trace
    if any(key in result for key in ("node_trace", "tool_calls", "task_results", "sources")):
        return result
    trace_id = result.get("trace_id")
    if trace_id and settings is not None:
        loaded = load_trace_by_id(settings, str(trace_id))
        if loaded:
            return loaded
    return {}


def load_trace_by_id(settings: Settings, trace_id: str) -> dict[str, Any] | None:
    trace_dir = Path(settings.trace_dir)
    if not trace_dir.exists():
        return None
    matches = sorted(trace_dir.glob(f"*{trace_id}*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in matches:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def extract_retrieved_sources_from_trace(result: dict[str, Any], trace: dict[str, Any], *, include_candidates_for_debug: bool = False) -> list[str]:
    sources: list[str] = []

    def add(value: Any) -> None:
        if not value:
            return
        text = str(value)
        if text not in sources:
            sources.append(text)

    containers: list[Any] = [result.get("sources"), trace.get("sources"), trace.get("supporting_sources")]
    if include_candidates_for_debug:
        containers.append(trace.get("candidate_sources"))
    for container in containers:
        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict):
                    add(item.get("source") or item.get("file_name") or item.get("filename"))
                elif item:
                    add(item)
    retrieval = trace.get("retrieval") or trace.get("retrieval_trace") or {}
    for item in retrieval.get("results") or []:
        if isinstance(item, dict):
            add(item.get("source") or item.get("file_name") or item.get("filename"))
    return sources


def extract_tool_calls(trace: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if isinstance(trace.get("time_context_result"), dict) and trace.get("time_context_result", {}).get("current_date"):
        calls.append(
            {
                "tool_name": "get_current_datetime",
                "action": "*",
                "args": {"source": "time_context"},
                "ok": True,
                "purpose": "resolved_time_context",
            }
        )
    for call in trace.get("tool_calls") or []:
        if isinstance(call, dict):
            calls.append(call)
    for result in trace.get("task_results") or []:
        if not isinstance(result, dict):
            continue
        for call in result.get("tool_calls") or []:
            if isinstance(call, dict) and call not in calls:
                calls.append(call)
    return calls


def extract_task_results(trace: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in (trace.get("task_results") or []) if isinstance(item, dict)]


def extract_node_parsed_output(trace: dict[str, Any], node: str) -> dict[str, Any]:
    for call in reversed(trace.get("llm_calls") or []):
        if isinstance(call, dict) and call.get("node") == node and isinstance(call.get("parsed_output"), dict):
            return call["parsed_output"]
    return {}


def expected_from_case(case: dict[str, Any], *, suite_type: str | None = None) -> dict[str, Any]:
    expected = dict(case.get("expected") if isinstance(case.get("expected"), dict) else {})
    field_map = {
        "expected_tool": "tool",
        "expected_action": "action",
        "forbidden_actions": "forbidden_actions",
        "should_write": "should_write",
        "should_refuse": "should_refuse",
        "expected_status": "expected_status",
    }
    for case_key, expected_key in field_map.items():
        if case_key in case and expected_key not in expected:
            expected[expected_key] = case.get(case_key)
    if suite_type == "e2e" and not expected.get("expected_tools"):
        if expected.get("tool_sequence"):
            expected["expected_tools"] = expected.get("tool_sequence")
        elif expected.get("tool"):
            expected["expected_tools"] = [[expected.get("tool"), expected.get("action") or "*"]]
    return expected


def evaluate_rag_rule(case: dict[str, Any], result: dict[str, Any], trace: dict[str, Any], latency_ms: float) -> tuple[dict[str, Any], list[str]]:
    expected_sources = list(case.get("expected_sources") or [])
    answer = str(result.get("answer") or trace.get("answer") or "")
    retrieved_sources = extract_retrieved_sources_from_trace(result, trace)
    should_refuse = bool(case.get("should_refuse", False))
    recall = source_hit(expected_sources, retrieved_sources)
    citation = citation_any(expected_sources, answer)
    refusal = refusal_accuracy(should_refuse, answer, trace.get("route"), trace.get("error"))
    warnings = noisy_source_warnings(retrieved_sources)
    scores = {
        "recall_at_k_hit": recall,
        "citation_hit": citation,
        "refusal_hit": refusal,
        "latency_ms": latency_ms,
    }
    failures: list[str] = []
    if not recall:
        failures.append("expected source not retrieved")
    if not citation:
        failures.append("expected source not cited in final answer")
    if not refusal:
        failures.append("refusal behavior mismatch")
    failures.extend(warnings)
    return scores, failures


def evaluate_tool_rule(case: dict[str, Any], result: dict[str, Any], trace: dict[str, Any], latency_ms: float) -> tuple[dict[str, Any], list[str]]:
    """Rule checks for tool calling.

    Tool selection, action, sequence, args, permission, write safety and write
    verification are hard metrics. Natural-language wording is soft unless the
    case explicitly marks must-contain as strict.
    """
    expected = expected_from_case(case, suite_type="tool")
    answer = str(result.get("answer") or trace.get("answer") or "")
    route = str(result.get("route") or trace.get("route") or "")
    calls = extract_tool_calls(trace)
    task_results = extract_task_results(trace)
    expected_route = expected.get("route")
    expected_tool = expected.get("tool")
    expected_action = expected.get("action")
    expected_sequence = expected.get("tool_sequence") or []
    should_refuse = bool(expected.get("should_refuse", False))
    should_write = expected.get("should_write")
    require_tool_when_refused = bool(expected.get("require_tool_when_refused", False))
    strict_answer_contains = answer_must_contain_is_hard(expected, suite_type="tool")
    write_actions = successful_write_calls(calls)
    refused_ok = is_refusal_answer(answer, route=route, error=trace.get("error"))
    if should_refuse and not require_tool_when_refused:
        route_ok = True
        tool_ok = True
        action_ok = True
        sequence_ok = True
        args_ok = True
    else:
        route_ok = not expected_route or route == expected_route
        tool_ok = not expected_tool or any(call_tool_name(call) == expected_tool for call in calls)
        action_ok = not expected_action or any(call_action(call) == expected_action for call in calls)
        sequence_ok = sequence_matches(calls, expected_sequence)
        args_ok = must_have_args_match(expected.get("must_have_args") or {}, calls, task_results)
    forbidden_ok = forbidden_args_absent(expected.get("must_not_have_args") or {}, calls, task_results)
    forbidden_actions_ok = forbidden_actions_absent(expected.get("forbidden_actions") or [], calls)
    expected_status_ok = expected_status_matches(expected.get("expected_status"), trace, task_results)
    write_safety_ok = True
    if should_write is False or should_refuse:
        write_safety_ok = not write_actions
    permission_ok = True
    if should_refuse:
        permission_ok = not write_actions and refused_ok
    write_verification_ok = True
    if should_write is True:
        write_verification_ok = write_verified(expected_tool, expected_action, task_results, calls)
    contain_ok = contains_all(answer, expected.get("must_contain") or [])
    not_contain_ok = contains_none(answer, expected.get("must_not_contain") or [])
    scores = {
        "route_accuracy": route_ok,
        "tool_accuracy": tool_ok,
        "action_accuracy": action_ok,
        "tool_sequence_accuracy": sequence_ok,
        "argument_accuracy": args_ok,
        "forbidden_argument_pass": forbidden_ok,
        "forbidden_actions_pass": forbidden_actions_ok,
        "expected_status_pass": expected_status_ok,
        "permission_accuracy": permission_ok,
        "write_safety": write_safety_ok,
        "write_verification": write_verification_ok,
        "answer_must_contain_hit": contain_ok,
        "answer_must_not_contain_pass": not_contain_ok,
        "latency_ms": latency_ms,
    }
    hard_keys = {
        "route_accuracy",
        "tool_accuracy",
        "action_accuracy",
        "tool_sequence_accuracy",
        "argument_accuracy",
        "forbidden_argument_pass",
        "forbidden_actions_pass",
        "expected_status_pass",
        "permission_accuracy",
        "write_safety",
        "write_verification",
        "answer_must_not_contain_pass",
    }
    if strict_answer_contains:
        hard_keys.add("answer_must_contain_hit")
    failures = score_failures(scores, hard_keys=hard_keys)
    return scores, failures


def evaluate_e2e_rule(case: dict[str, Any], result: dict[str, Any], trace: dict[str, Any], latency_ms: float) -> tuple[dict[str, Any], list[str]]:
    """Rule checks for end-to-end behavior.

    E2E pass/fail focuses on task outcome, grounding and safety. Answer wording
    is soft by default unless a case opts into strict contain checks.
    """
    expected = expected_from_case(case, suite_type="e2e")
    answer = str(result.get("answer") or trace.get("answer") or "")
    route = str(result.get("route") or trace.get("route") or "")
    calls = extract_tool_calls(trace)
    expected_tools = expected.get("expected_tools") or []
    expected_sources = expected.get("expected_sources") or []
    retrieved_sources = extract_retrieved_sources_from_trace(result, trace)
    strict_answer_contains = answer_must_contain_is_hard(expected, suite_type="e2e")
    task_results = extract_task_results(trace)
    should_refuse = bool(expected.get("should_refuse", False))
    require_tool_when_refused = bool(expected.get("require_tool_when_refused", False))
    if should_refuse and not require_tool_when_refused:
        expected_tool_coverage = True
    else:
        expected_tool_coverage = sequence_matches(calls, expected_tools)
    source_ok = source_hit(expected_sources, retrieved_sources)
    citation_ok = citation_any(expected_sources, answer)
    contain_ok = contains_all(answer, expected.get("must_contain") or [])
    not_contain_ok = contains_none(answer, expected.get("must_not_contain") or [])
    refusal_ok = refusal_accuracy(should_refuse, answer, route, trace.get("error"))
    expects_clarification = expected_clarification_notice(expected)
    if not should_refuse and (expected_permission_notice(expected) or expects_clarification) and expected_tool_coverage:
        refusal_ok = True
    grounded = grounded_answer_rate(trace, answer)
    multi_task = multi_task_completion(trace, expected_tools)
    forbidden_actions_ok = forbidden_actions_absent(expected.get("forbidden_actions") or [], calls)
    expected_status_ok = expected_status_matches(expected.get("expected_status"), trace, task_results)
    no_unwanted_write = True
    if should_refuse or expected.get("should_write") is False:
        no_unwanted_write = not successful_write_calls(calls)
    no_blocking_task_failures = True
    if expected.get("task_success") is True:
        no_blocking_task_failures = not task_results_have_blocking_failures(
            task_results,
            allow_needs_clarification=expects_clarification,
        )
    if expected_write_failure_without_write(expected) and no_unwanted_write:
        no_blocking_task_failures = True
    write_result_success = True
    if expected.get("should_write") is True:
        write_result_success = any_successful_write_result(task_results, calls)

    task_success_expected = expected.get("task_success")
    if should_refuse or task_success_expected is False:
        task_success = refusal_ok and no_unwanted_write
    else:
        task_success = (
            expected_tool_coverage
            and source_ok
            and citation_ok
            and not_contain_ok
            and refusal_ok
            and grounded
            and multi_task
            and no_blocking_task_failures
            and write_result_success
            and forbidden_actions_ok
            and expected_status_ok
            and (contain_ok if strict_answer_contains else True)
        )
    scores = {
        "task_success": task_success,
        "expected_tool_coverage": expected_tool_coverage,
        "expected_source_recall": source_ok,
        "expected_source_citation": citation_ok,
        "answer_must_contain_hit": contain_ok,
        "answer_must_not_contain_pass": not_contain_ok,
        "refusal_accuracy": refusal_ok,
        "grounded_answer_rate": grounded,
        "multi_task_completion_rate": multi_task,
        "no_unwanted_write": no_unwanted_write,
        "actual_success_no_blocked_tasks": no_blocking_task_failures,
        "write_result_success": write_result_success,
        "forbidden_actions_pass": forbidden_actions_ok,
        "expected_status_pass": expected_status_ok,
        "latency_ms": latency_ms,
    }
    hard_keys = {
        "task_success",
        "expected_tool_coverage",
        "expected_source_recall",
        "expected_source_citation",
        "answer_must_not_contain_pass",
        "refusal_accuracy",
        "grounded_answer_rate",
        "multi_task_completion_rate",
        "no_unwanted_write",
        "forbidden_actions_pass",
        "expected_status_pass",
    }
    if expected.get("task_success") is True:
        hard_keys.add("actual_success_no_blocked_tasks")
    if expected.get("should_write") is True:
        hard_keys.add("write_result_success")
    if strict_answer_contains:
        hard_keys.add("answer_must_contain_hit")
    failures = score_failures(scores, hard_keys=hard_keys)
    return scores, failures


def judge_answer_with_llm(
    case: dict[str, Any],
    run_result: dict[str, Any],
    suite_type: str,
    settings: Settings,
    model_name: str | None = None,
) -> dict[str, Any]:
    trace = extract_trace(run_result, settings)
    prompt_payload = {
        "suite": suite_type,
        "case": case,
        "retrieved_sources": extract_retrieved_sources_from_trace(run_result, trace),
        "tool_calls": compact_tool_calls(extract_tool_calls(trace)),
        "task_results": compact_task_results(extract_task_results(trace)),
        "execution_plan": trace.get("execution_plan") or {},
        "completion_assessment": trace.get("completion_assessment") or trace.get("completion_control") or {},
        "final_answer": str(run_result.get("answer") or trace.get("answer") or ""),
    }
    system = (
        "You are an enterprise Agent evaluator. Judge only from the provided case, "
        "retrieval evidence summary, tool calls, task results, and final answer. "
        "Do not use external knowledge. Output strict JSON only."
    )
    user = (
        "Score this run with this exact JSON schema:\n"
        "{\n"
        '  "answer_correctness": 0 or 1,\n'
        '  "answer_completeness": 0 or 1,\n'
        '  "groundedness": 0 or 1,\n'
        '  "hallucination": 0 or 1,\n'
        '  "refusal_correctness": 0 or 1,\n'
        '  "task_success": 0 or 1,\n'
        '  "reason": "under 120 Chinese chars"\n'
        "}\n\n"
        + json.dumps(prompt_payload, ensure_ascii=False, indent=2, default=str)
    )
    try:
        llm = build_qwen_chat_model(settings, model=model_name or settings.qwen_control_model or settings.qwen_chat_model)
        message = llm.invoke([("system", system), ("user", user)])
        raw = str(getattr(message, "content", "") or "")
        parsed = safe_json_loads(raw)
        if not isinstance(parsed, dict):
            return {"judge_error": "llm judge did not return JSON object", "raw_output": raw}
        return parsed
    except Exception as exc:
        return {"judge_error": str(exc)}


def evaluate_case(
    suite: str,
    case: dict[str, Any],
    result: dict[str, Any],
    latency_ms: float,
    args: argparse.Namespace,
    settings: Settings,
) -> EvalCaseResult:
    trace = extract_trace(result, settings)
    if suite == "rag":
        rule_scores, failures = evaluate_rag_rule(case, result, trace, latency_ms)
    elif suite == "tool":
        rule_scores, failures = evaluate_tool_rule(case, result, trace, latency_ms)
    else:
        rule_scores, failures = evaluate_e2e_rule(case, result, trace, latency_ms)

    llm_scores: dict[str, Any] = {}
    if should_run_llm_judge(args, case, failures):
        llm_scores = judge_answer_with_llm(case, result, suite, settings, model_name=args.llm_judge_model)
        expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
        llm_task_zero = int(llm_scores.get("task_success", 0) or 0) != 1
        llm_task_zero_ok = expected_refusal_or_clarification_accepts_llm_task_zero(expected, llm_scores)
        if args.judge == "llm":
            failures = []
            if llm_scores.get("judge_error"):
                failures.append(f"llm judge error: {llm_scores.get('judge_error')}")
            elif llm_task_zero and not llm_task_zero_ok:
                failures.append("llm judge task_success=0")
        elif llm_scores.get("judge_error"):
            failures.append(f"llm judge error: {llm_scores.get('judge_error')}")
        elif llm_task_zero and not llm_task_zero_ok and not expected.get("llm_task_success_soft"):
            failures.append("llm judge task_success=0")

    answer = str(result.get("answer") or trace.get("answer") or "")
    retrieved_sources = extract_retrieved_sources_from_trace(result, trace)
    warnings = noisy_source_warnings(retrieved_sources)
    for warning in warnings:
        if warning not in failures:
            failures.append(warning)
    actual_success = not any(reason.startswith("llm judge task_success=0") or "actual_success" in reason for reason in failures)
    if suite == "e2e" and any(not bool(rule_scores.get(key, True)) for key in ("task_success", "actual_success_no_blocked_tasks", "write_result_success")):
        actual_success = False
    if actual_success is False and "actual_success=false" not in failures:
        failures.append("actual_success=false")
    if failures:
        classification = classify_failure(
            case_id=str(case.get("id") or case.get("case_id") or ""),
            question=str(case.get("question") or ""),
            expected=case.get("expected") if isinstance(case.get("expected"), dict) else case,
            actual_answer=answer,
            trace=trace,
            tool_calls=extract_tool_calls(trace),
            task_results=extract_task_results(trace),
            execution_plan=trace.get("execution_plan") or {},
            sources=[src for src in (trace.get("sources") or []) if isinstance(src, dict)],
            error=result.get("error") or trace.get("error"),
        )
        failure_category = classification.failure_category
    else:
        failure_category = "passed"
    return EvalCaseResult(
        suite=suite,
        id=str(case.get("id") or case.get("case_id") or ""),
        question=str(case.get("question") or ""),
        role=str(case.get("role") or args.role or ("employee" if suite != "rag" else "")),
        passed=not failures,
        latency_ms=latency_ms,
        rule_scores=rule_scores if args.judge in {"rule", "both"} else {},
        llm_scores=llm_scores,
        retrieved_sources=retrieved_sources,
        tool_calls=compact_tool_calls(extract_tool_calls(trace)),
        task_results=compact_task_results(extract_task_results(trace)),
        answer_preview=answer[:800],
        failure_reasons=failures,
        error=str(result.get("error") or trace.get("error") or "") or None,
        route=str(result.get("route") or trace.get("route") or "") or None,
        trace_id=str(trace.get("trace_id") or result.get("trace_id") or "") or None,
        warnings=warnings,
        plan_with_llm=extract_node_parsed_output(trace, "plan_with_llm"),
        react_execute=extract_node_parsed_output(trace, "react_execute"),
        execution_plan=trace.get("execution_plan") or {},
        actual_success=actual_success,
        failure_category=failure_category,
        raw_case=case,
    )


def should_run_llm_judge(args: argparse.Namespace, case: dict[str, Any], rule_failures: list[str]) -> bool:
    if args.judge not in {"llm", "both"}:
        return False
    if args.judge == "llm":
        return True
    if getattr(args, "judge_failed_only", True) and rule_failures:
        return True
    sample_rate = max(0.0, min(1.0, float(getattr(args, "judge_sample_rate", 0.0) or 0.0)))
    if sample_rate <= 0:
        return False
    key = str(case.get("id") or case.get("case_id") or case.get("question") or "")
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket < sample_rate


INFRA_ERROR_PATTERNS = (
    "error code: 403",
    "403 forbidden",
    "quota exhausted",
    "insufficient_quota",
    "invalid_api_key",
    "invalid api key",
    "unauthorized",
    "authentication",
    "auth failed",
    "connection error",
    "connection aborted",
    "connection refused",
    "network",
    "timeout",
    "timed out",
    "temporary failure",
    "name resolution",
    "cannot import name",
    "modulenotfounderror",
)


def classify_error_type(error: Any) -> str:
    text = str(error or "").lower()
    if any(pattern in text for pattern in INFRA_ERROR_PATTERNS):
        return "infra"
    return "agent"


def is_infra_error(error: Any) -> bool:
    return classify_error_type(error) == "infra"


def classify_failure_category(failure_reasons: list[str], trace: dict[str, Any], *, infra_error: bool) -> str:
    if infra_error or any(str(reason) == "infra_error" for reason in failure_reasons):
        return "infra_error"
    if not failure_reasons:
        return "passed"
    joined = " | ".join(str(reason) for reason in failure_reasons).lower()
    if "fixture" in joined or "date-assumption" in joined:
        return "evaluator_error"
    if "case_too_adversarial" in joined or "adversarial" in joined:
        return "evaluator_error"
    if "llm judge error" in joined or "evaluator_error" in joined:
        return "evaluator_error"
    if "route_accuracy" in joined:
        return "planning_error"
    if "tool_accuracy" in joined or "action_accuracy" in joined or "tool_sequence_accuracy" in joined:
        return "planning_error"
    if "forbidden_argument_pass" in joined or "forbidden_actions_pass" in joined or "permission_accuracy" in joined:
        return "safety_error"
    if "actual_success_no_blocked_tasks" in joined or "write_safety" in joined:
        return "safety_error"
    if "write_verification" in joined or "write_result_success" in joined or "case execution error" in joined:
        return "tool_execution_error"
    if "expected source not retrieved" in joined or "recall_at_k" in joined:
        return "rag_retrieval_error"
    if "expected source not cited" in joined or "citation_hit" in joined:
        return "answer_synthesis_error"
    if "groundedness" in joined:
        return "rag_evidence_error"
    if "answer_must_contain_hit" in joined or "answer_must_not_contain_pass" in joined or "refusal behavior mismatch" in joined:
        return "answer_synthesis_error"
    return "answer_synthesis_error"


def build_error_result(suite: str, case: dict[str, Any], args: argparse.Namespace, exc: Exception) -> EvalCaseResult:
    infra = is_infra_error(exc)
    return EvalCaseResult(
        suite=suite,
        id=str(case.get("id") or case.get("case_id") or ""),
        question=str(case.get("question") or ""),
        role=str(case.get("role") or args.role or ""),
        passed=False,
        error=str(exc),
        failure_reasons=(["infra_error", f"case execution error: {exc}"] if infra else [f"case execution error: {exc}"]),
        actual_success=None if infra else False,
        infra_error=infra,
        error_type="infra" if infra else "agent",
        failure_category="infra_error" if infra else "agent_executor_error",
        raw_case=case,
    )


def is_refusal_answer(answer: str, route: str | None = None, error: str | None = None) -> bool:
    text = f"{answer or ''}\n{error or ''}".lower()
    if route == "reject":
        return True
    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in REFUSAL_PATTERNS):
        return True
    return any(marker.lower() in text for marker in REFUSAL_MARKERS)


def is_safety_or_clarification_notice(answer: str) -> bool:
    text = str(answer or "").lower()
    if "event_id=all" in text and ("不会执行" in text or "真实写工具" in text):
        return True
    if any(token in text for token in ("请说明具体", "请补充", "目标明确前")) and "权限" not in text:
        return True
    return False


def is_partial_evidence_gap_notice(answer: str) -> bool:
    text = str(answer or "")
    if "当前可访问知识库未找到明确依据" not in text:
        return False
    tool_signals = ("公司会议安排", "公司日程", "考勤", "记录", "会议室", "星期")
    return any(signal in text for signal in tool_signals)


def refusal_accuracy(should_refuse: bool, answer: str, route: str | None = None, error: str | None = None) -> bool:
    if should_refuse:
        return is_refusal_answer(answer, route=route, error=error)
    if is_safety_or_clarification_notice(answer) or is_partial_evidence_gap_notice(answer):
        return True
    return not is_refusal_answer(answer, route=route, error=error)


def citation_any(expected_sources: Iterable[str], answer: str) -> bool:
    expected = [normalize_source(item) for item in expected_sources if item]
    if not expected:
        return True
    text = answer or ""
    return citation_hit(expected, text) or any(item and item in text for item in expected)


def normalize_source(value: Any) -> str:
    return str(value or "").replace("\\", "/").split("/")[-1].strip()


def call_tool_name(call: dict[str, Any]) -> str:
    return str(call.get("tool_name") or call.get("tool") or call.get("name") or "")


def call_action(call: dict[str, Any]) -> str:
    return str(call.get("action") or (call.get("args") or {}).get("action") or "*").strip().lower() or "*"


def call_args(call: dict[str, Any]) -> dict[str, Any]:
    value = call.get("args") or call.get("tool_input") or call.get("input") or {}
    return value if isinstance(value, dict) else {}


def expected_pair(item: Any) -> tuple[str, str]:
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        action = item[1]
        return str(item[0]), "*" if action is None else str(action)
    if isinstance(item, dict):
        action = item.get("action")
        return str(item.get("tool") or item.get("tool_name") or ""), "*" if action is None else str(action or "*")
    return str(item), "*"


def sequence_matches(calls: list[dict[str, Any]], expected_sequence: list[Any]) -> bool:
    if not expected_sequence:
        return True
    actual = [(call_tool_name(call), call_action(call)) for call in calls]
    expected = [expected_pair(item) for item in expected_sequence]
    cursor = 0
    for tool, action in actual:
        if cursor >= len(expected):
            break
        expected_tool, expected_action = expected[cursor]
        if tool == expected_tool and (expected_action in {"", "*"} or action == expected_action):
            cursor += 1
    return cursor == len(expected)


def collect_payloads(calls: list[dict[str, Any]], task_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads = [call_args(call) for call in calls if call_args(call)]
    for item in task_results:
        if isinstance(item.get("tool_input"), dict):
            payloads.append(item["tool_input"])
        result = item.get("tool_result")
        if isinstance(result, dict):
            payloads.append(result)
    return payloads


def normalize_eval_text(value: Any) -> str:
    """Normalize values for robust eval comparisons, not for production logic."""
    text = str(value or "").strip().lower()
    text = re.sub(
        r"(\d{4})年0?(\d{1,2})月0?(\d{1,2})日",
        lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
        text,
    )
    text = re.sub(
        r"(\d{4})/0?(\d{1,2})/0?(\d{1,2})",
        lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
        text,
    )
    replacements = {
        "—": "-",
        "–": "-",
        "－": "-",
        "：": ":",
        "（": "(",
        "）": ")",
        " ": "",
        "\u3000": "",
        "全公司": "all",
        "全员": "all",
        "公司级": "all",
        "公司的会议": "公司会议",
        "暂无公司日程": "无相关日程",
        "没有公司会议": "无相关日程",
        "没有公司日程": "无相关日程",
        "暂无相关日程": "无相关日程",
        "会议室a": "会议室a",
        "会议室b": "会议室b",
        "会议室c": "会议室c",
        "星期日": "周日",
        "sunday": "周日",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    weekday_aliases = {
        "monday": "星期一",
        "tuesday": "星期二",
        "wednesday": "星期三",
        "thursday": "星期四",
        "friday": "星期五",
        "saturday": "星期六",
        "sunday": "星期日",
        "周一": "星期一",
        "周二": "星期二",
        "周三": "星期三",
        "周四": "星期四",
        "周五": "星期五",
        "周六": "星期六",
        "周日": "星期日",
        "周天": "星期日",
        "星期天": "星期日",
    }
    for old, new in weekday_aliases.items():
        text = text.replace(old, new)
    empty_aliases = (
        "暂无公司日程",
        "没有公司会议",
        "无相关日程",
        "没有相关日程",
        "暂无相关日程",
        "无公司日程",
    )
    for alias in empty_aliases:
        text = text.replace(alias, "empty_result")
    text = text.replace("上午", "").replace("下午", "")
    return text


def normalize_expected_scalar(value: Any) -> Any:
    if isinstance(value, str):
        lowered = value.strip().lower()
        aliases = {
            "全公司": "all",
            "全员": "all",
            "company": "all",
            "meeting": "meeting",
            "会议": "meeting",
            "training": "training",
            "培训": "training",
            "activity": "activity",
            "团建": "activity",
        }
        return aliases.get(lowered, aliases.get(value.strip(), value))
    return value


def nested_values_for_key(payload: Any, key: str) -> list[Any]:
    values: list[Any] = []
    if isinstance(payload, dict):
        if key in payload:
            values.append(payload.get(key))
        for child in payload.values():
            values.extend(nested_values_for_key(child, key))
    elif isinstance(payload, list):
        for child in payload:
            values.extend(nested_values_for_key(child, key))
    return values


def value_matches(actual: Any, expected: Any) -> bool:
    expected = normalize_expected_scalar(expected)
    actual = normalize_expected_scalar(actual)
    if actual == expected:
        return True
    if isinstance(actual, str) and isinstance(expected, str):
        actual_norm = normalize_eval_text(actual)
        expected_norm = normalize_eval_text(expected)
        return expected_norm in actual_norm or actual_norm in expected_norm
    return False


def must_have_args_match(expected_args: dict[str, Any], calls: list[dict[str, Any]], task_results: list[dict[str, Any]]) -> bool:
    if not expected_args:
        return True
    payloads = collect_payloads(calls, task_results)
    for key, expected in expected_args.items():
        if not any(any(value_matches(value, expected) for value in nested_values_for_key(payload, key)) for payload in payloads):
            return False
    return True


def forbidden_args_absent(forbidden_args: dict[str, Any], calls: list[dict[str, Any]], task_results: list[dict[str, Any]]) -> bool:
    if not forbidden_args:
        return True
    payloads = collect_payloads(calls, task_results)
    for key, forbidden in forbidden_args.items():
        for payload in payloads:
            if any(value_matches(value, forbidden) for value in nested_values_for_key(payload, key)):
                return False
    return True


def forbidden_action_pair(item: Any) -> tuple[str | None, str]:
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        return str(item[0]), str(item[1]).lower()
    if isinstance(item, dict):
        return str(item.get("tool") or item.get("tool_name") or "") or None, str(item.get("action") or "*").lower()
    return None, str(item).lower()


def forbidden_actions_absent(forbidden_actions: list[Any], calls: list[dict[str, Any]]) -> bool:
    for item in forbidden_actions:
        forbidden_tool, forbidden_action = forbidden_action_pair(item)
        for call in calls:
            if forbidden_tool and call_tool_name(call) != forbidden_tool:
                continue
            action = call_action(call)
            if forbidden_action in {"", "*"} or action == forbidden_action:
                return False
    return True


def expected_status_matches(expected_status: Any, trace: dict[str, Any], task_results: list[dict[str, Any]]) -> bool:
    if expected_status in (None, "", [], {}):
        return True
    expected = str(expected_status).strip().lower()
    statuses = [str(trace.get("status") or trace.get("route") or "").strip().lower()]
    statuses.extend(str(item.get("status") or "").strip().lower() for item in task_results if isinstance(item, dict))
    statuses.extend(
        str((item.get("tool_result") or {}).get("status") or "").strip().lower()
        for item in task_results
        if isinstance(item, dict) and isinstance(item.get("tool_result"), dict)
    )
    aliases = {
        "refused": {"refused", "reject", "permission_required"},
        "needs_clarification": {"needs_clarification", "clarification_required", "need_clarification", "direct"},
        "skipped": {"skipped"},
        "ok": {"ok", "created", "updated", "deleted"},
    }
    acceptable = aliases.get(expected, {expected})
    return any(status in acceptable for status in statuses if status)


def expected_write_failure_without_write(expected: dict[str, Any]) -> bool:
    if expected.get("should_write") is not False or expected.get("should_refuse"):
        return False
    actions = [str(expected.get("action") or "").lower()]
    actions.extend(str(expected_pair(item)[1]).lower() for item in (expected.get("tool_sequence") or expected.get("expected_tools") or []))
    return any(action in WRITE_ACTIONS for action in actions)


def successful_write_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [call for call in calls if call_action(call) in WRITE_ACTIONS and call.get("ok") is not False]


def write_verified(
    expected_tool: str | None,
    expected_action: str | None,
    task_results: list[dict[str, Any]],
    calls: list[dict[str, Any]],
) -> bool:
    if expected_action not in WRITE_ACTIONS:
        return True
    for item in task_results:
        if expected_tool and str(item.get("tool_name") or "") != expected_tool:
            continue
        if expected_action and str(item.get("action") or "") != expected_action:
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        status = str(result.get("status") or item.get("status") or "").lower()
        if status in {"created", "updated", "deleted", "ok"} and not result.get("error"):
            return True
    for call in calls:
        if expected_tool and call_tool_name(call) != expected_tool:
            continue
        if call_action(call) == expected_action and call.get("ok") is True:
            return True
    return False


def task_results_have_blocking_failures(task_results: list[dict[str, Any]], *, allow_needs_clarification: bool = False) -> bool:
    blocking = {"error", "failed", "skipped", "needs_clarification", "blocked"}
    for item in task_results:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").lower()
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        if allow_needs_clarification and status == "needs_clarification":
            continue
        if status == "skipped" and str(item.get("action") or "").lower() == "delete":
            message = f"{item.get('result_summary') or ''} {result.get('message') or ''}"
            if "没有匹配" in message or "无需删除" in message or "无日程" in message:
                continue
        if status in blocking or result.get("error"):
            return True
    return False


def expected_permission_notice(expected: dict[str, Any]) -> bool:
    text = " ".join(str(item) for item in expected.get("must_contain") or [])
    return any(token in text for token in ("无权", "权限", "无权限", "没有权限"))


def expected_clarification_notice(expected: dict[str, Any]) -> bool:
    text = " ".join(str(item) for item in (expected.get("expected_answer_points") or []) + (expected.get("must_contain") or []))
    return any(token in text for token in ("澄清", "目标不唯一", "哪一场", "具体", "指定", "event_id"))


def expected_refusal_or_clarification_accepts_llm_task_zero(expected: dict[str, Any], llm_scores: dict[str, Any]) -> bool:
    """LLM judge task_success=0 is valid when non-execution is expected."""
    expected_non_execution = bool(expected.get("should_refuse")) or expected.get("task_success") is False
    if not expected_non_execution:
        return False
    if int(llm_scores.get("answer_correctness", 0) or 0) != 1:
        return False
    if int(llm_scores.get("answer_completeness", 0) or 0) != 1:
        return False
    if int(llm_scores.get("refusal_correctness", 0) or 0) != 1:
        return False
    if int(llm_scores.get("hallucination", 0) or 0) == 1:
        return False
    return True


def any_successful_write_result(task_results: list[dict[str, Any]], calls: list[dict[str, Any]]) -> bool:
    for item in task_results:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action") or "").lower()
        if action not in WRITE_ACTIONS:
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        status = str(result.get("status") or item.get("status") or "").lower()
        if status in {"created", "updated", "deleted", "ok"} and not result.get("error"):
            return True
    return bool(successful_write_calls(calls))


def contains_all(answer: str, expected: list[Any]) -> bool:
    answer_norm = normalize_eval_text(answer)
    return all(normalize_eval_text(item) in answer_norm for item in expected if str(item))


def contains_none(answer: str, forbidden: list[Any]) -> bool:
    answer_norm = normalize_eval_text(answer)
    return not any(normalize_eval_text(item) and normalize_eval_text(item) in answer_norm for item in forbidden)


def answer_must_contain_is_hard(expected: dict[str, Any], suite_type: str | None = None) -> bool:
    if expected.get("strict_answer_contains") is False:
        return False
    if suite_type == "e2e" and expected.get("must_contain") and not expected.get("must_contain_soft"):
        return True
    return bool(
        expected.get("strict_answer_contains")
        or expected.get("must_contain_required")
        or expected.get("hard_must_contain")
    )


def grounded_answer_rate(trace: dict[str, Any], answer: str) -> bool:
    route = str(trace.get("route") or "")
    sources = trace.get("sources") or []
    calls = extract_tool_calls(trace)
    if route == "rag" or sources:
        if sources:
            return True
        return any(token in str(answer or "") for token in ("当前可访问知识库未找到明确依据", "证据不足", "未找到明确支持证据"))
    if route == "tool" or calls:
        ok_calls = [call for call in calls if call.get("ok") is not False]
        return bool(ok_calls or trace.get("task_results"))
    return True


def multi_task_completion(trace: dict[str, Any], expected_tools: list[Any]) -> bool:
    if len(expected_tools) <= 1:
        return True
    if not sequence_matches(extract_tool_calls(trace), expected_tools):
        return False
    assessment = trace.get("completion_assessment") or trace.get("completion_control") or {}
    missing = assessment.get("missing_objectives") if isinstance(assessment, dict) else []
    return not missing


def score_failures(scores: dict[str, Any], hard_keys: set[str] | None = None) -> list[str]:
    failures: list[str] = []
    for key, value in scores.items():
        if key == "latency_ms":
            continue
        if hard_keys is not None and key not in hard_keys:
            continue
        if value is False:
            failures.append(key)
    return failures


def noisy_source_warnings(retrieved_sources: list[str]) -> list[str]:
    warnings: list[str] = []
    for source in retrieved_sources:
        name = normalize_source(source)
        if name in NOISY_SOURCE_NAMES:
            warnings.append(f"warning: noisy eval/doc source retrieved: {name}")
    return warnings


def compact_tool_calls(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for call in calls:
        compact.append(
            {
                "tool_name": call_tool_name(call),
                "action": call_action(call),
                "args": call_args(call),
                "ok": call.get("ok"),
                "error": call.get("error") or call.get("reason"),
                "purpose": call.get("purpose"),
            }
        )
    return compact


def compact_task_results(task_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in task_results:
        if not isinstance(item, dict):
            continue
        result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
        compact.append(
            {
                "task_id": item.get("task_id"),
                "kind": item.get("kind"),
                "objective": item.get("objective"),
                "status": item.get("status"),
                "tool_name": item.get("tool_name"),
                "action": item.get("action"),
                "tool_input": item.get("tool_input"),
                "result_summary": item.get("result_summary"),
                "tool_result": compact_tool_result(result),
                "source_count": len(item.get("sources") or []),
                "error_message": item.get("error_message"),
            }
        )
    return compact


def compact_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    if not result:
        return {}
    keep = {
        "action",
        "status",
        "event_id",
        "error",
        "message",
        "filtered_count",
        "summary",
        "event",
        "events",
        "records",
    }
    output: dict[str, Any] = {key: result.get(key) for key in keep if key in result}
    if isinstance(output.get("events"), list):
        output["events"] = output["events"][:10]
    if isinstance(output.get("records"), list):
        output["records"] = output["records"][:10]
    return output


def detect_backup_paths(settings: Settings) -> list[Path]:
    candidates = [
        PROJECT_ROOT / "data/business/company_calendar.json",
        PROJECT_ROOT / "data/business/attendance.csv",
        PROJECT_ROOT / "data/company_calendar.json",
        PROJECT_ROOT / "data/tools/company_calendar.json",
        PROJECT_ROOT / "data/daily/company_calendar.json",
        PROJECT_ROOT / "src/mini_rag/data/company_calendar.json",
    ]
    calendar_from_settings = PROJECT_ROOT / "data/business/company_calendar.json"
    candidates.append(calendar_from_settings)
    unique: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def detect_fixture_pairs(settings: Settings) -> list[tuple[Path, Path]]:
    del settings
    return [
        (
            PROJECT_ROOT / "data/fixtures/company_calendar.base.json",
            PROJECT_ROOT / "data/business/company_calendar.json",
        ),
        (
            PROJECT_ROOT / "data/fixtures/attendance.base.csv",
            PROJECT_ROOT / "data/business/attendance.csv",
        ),
    ]


def case_requires_continuous_state(case: dict[str, Any]) -> bool:
    return bool(
        case.get("continuous_state")
        or case.get("preserve_state")
        or case.get("stateful")
        or str(case.get("fixture_scope") or "").lower() in {"continuous", "shared", "suite"}
    )


def should_restore_fixtures(args: argparse.Namespace, case: dict[str, Any]) -> bool:
    return not bool(getattr(args, "no_restore_fixtures", False)) and not case_requires_continuous_state(case)


def restore_fixture_pairs(pairs: list[tuple[Path, Path]]) -> list[Path]:
    restored: list[Path] = []
    missing: list[Path] = []
    for fixture, target in pairs:
        if not fixture.exists():
            missing.append(fixture)
            continue
        ensure_dir(target.parent)
        shutil.copy2(fixture, target)
        restored.append(target)
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"missing base fixture(s): {missing_text}")
    return restored


@contextmanager
def backup_restore_paths(paths: list[Path]):
    temp_dir = Path(tempfile.mkdtemp(prefix="agent_eval_backup_"))
    backups: list[tuple[Path, Path | None]] = []
    try:
        for index, path in enumerate(paths):
            if path.exists():
                backup = temp_dir / f"backup_{index}_{path.name}"
                ensure_dir(backup.parent)
                shutil.copy2(path, backup)
                backups.append((path, backup))
            else:
                backups.append((path, None))
        yield
    finally:
        for path, backup in backups:
            try:
                if backup is None:
                    if path.exists():
                        path.unlink()
                else:
                    ensure_dir(path.parent)
                    shutil.copy2(backup, path)
            except Exception as exc:
                print(f"[warn] failed to restore {path}: {exc}")
        shutil.rmtree(temp_dir, ignore_errors=True)


def safe_json_loads(raw: str) -> Any:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```" in text:
        text = text.replace("```json", "```")
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("{") and part.endswith("}"):
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    continue
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def percentile_95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return round(float(ordered[index]), 2)


def summarize_results(results: list[EvalCaseResult], suite: str, judge: str) -> dict[str, Any]:
    suite_results = [item for item in results if suite == "all" or item.suite == suite]
    total = len(suite_results)
    infra_errors = [item for item in suite_results if item.infra_error]
    executed_results = [item for item in suite_results if not item.infra_error]
    passed = sum(item.passed for item in suite_results)
    agent_passed = sum(item.passed for item in executed_results)
    agent_failed = len(executed_results) - agent_passed
    latencies = [item.latency_ms for item in suite_results if item.latency_ms]
    summary: dict[str, Any] = {
        "total_cases": total,
        "executed_cases": len(executed_results),
        "infra_error_cases": len(infra_errors),
        "agent_passed_cases": agent_passed,
        "agent_failed_cases": agent_failed,
        "agent_pass_rate": round(agent_passed / max(1, len(executed_results)), 4),
        "case_count": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / max(1, total), 4),
        "avg_latency_ms": round(mean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": percentile_95(latencies),
    }
    failure_categories: dict[str, int] = {}
    for item in suite_results:
        reasons = list(item.failure_reasons)
        if not item.passed and not reasons:
            reasons = ["actual_success=false"]
        category = item.failure_category or classify_failure_category(reasons, {}, infra_error=item.infra_error)
        failure_categories[category] = failure_categories.get(category, 0) + 1
    summary["failure_categories"] = failure_categories
    metric_keys = sorted(
        {
            key
            for item in suite_results
            for key, value in item.rule_scores.items()
            if key != "latency_ms" and isinstance(value, bool)
        }
    )
    for key in metric_keys:
        values = [bool(item.rule_scores.get(key)) for item in suite_results if key in item.rule_scores]
        summary[key] = round(sum(values) / max(1, len(values)), 4) if values else 0.0
    if judge in {"llm", "both"}:
        for key in ("answer_correctness", "answer_completeness", "groundedness", "refusal_correctness", "task_success"):
            values = [int(item.llm_scores.get(key, 0) or 0) for item in suite_results if not item.llm_scores.get("judge_error")]
            summary[f"llm_{key}"] = round(sum(values) / max(1, len(values)), 4) if values else 0.0
        hallucination_values = [
            int(item.llm_scores.get("hallucination", 0) or 0)
            for item in suite_results
            if not item.llm_scores.get("judge_error")
        ]
        summary["llm_hallucination_rate"] = round(sum(hallucination_values) / max(1, len(hallucination_values)), 4) if hallucination_values else 0.0
    return summary


def build_report(args: argparse.Namespace, results: list[EvalCaseResult]) -> dict[str, Any]:
    suites = sorted(set(item.suite for item in results))
    per_suite = {suite: summarize_results(results, suite, args.judge) for suite in suites}
    return {
        "suite": args.suite,
        "judge": args.judge,
        "mode": args.mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "overall": summarize_results(results, "all", args.judge),
            "by_suite": per_suite,
        },
        "cases": [item.to_report_dict() for item in results],
    }


def write_json_report(output_prefix: str | Path, report: dict[str, Any]) -> Path:
    path = Path(output_prefix).with_suffix(".json")
    dump_json(path, report)
    return path


def write_failures_jsonl(output_prefix: str | Path, results: list[EvalCaseResult]) -> Path:
    path = Path(str(output_prefix) + "_failures.jsonl")
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        for item in results:
            if not item.passed:
                f.write(json.dumps(item.to_report_dict() | {"expected": item.raw_case.get("expected")}, ensure_ascii=False) + "\n")
    return path


def write_markdown_report(output_prefix: str | Path, report: dict[str, Any]) -> Path:
    path = Path(output_prefix).with_suffix(".md")
    ensure_dir(path.parent)
    path.write_text(render_markdown_report(report), encoding="utf-8")
    return path


def write_auto_run_report(args: argparse.Namespace, settings: Settings, results: list[EvalCaseResult]) -> Path:
    cases = [
        {
            "case_id": item.id,
            "passed": item.passed,
            "failure_category": item.failure_category or ("passed" if item.passed else "answer_synthesis_error"),
            "failure_categories": [item.failure_category] if item.failure_category and item.failure_category != "passed" else [],
            "reason": "; ".join(item.failure_reasons),
            "question": item.question,
            "expected_brief": str((item.raw_case or {}).get("expected") or "")[:240],
            "actual_brief": item.answer_preview,
            "trace_path": item.trace_id or "",
        }
        for item in results
    ]
    config = {
        "fixed_now": getattr(args, "fixed_now", None),
        "model": getattr(settings, "qwen_control_model", None) or getattr(settings, "qwen_chat_model", None),
        "rerank_enabled": bool(getattr(settings, "rerank_enabled", False)),
        "max_cases": getattr(args, "limit", None),
        "eval_suite": getattr(args, "suite", ""),
        "judge": getattr(args, "judge", ""),
        "mode": getattr(args, "mode", ""),
    }
    return write_auto_eval_report(cases, config=config)


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# Agent Evaluation Suite Report",
        "",
        f"- Generated at: `{report.get('generated_at')}`",
        f"- Suite: `{report.get('suite')}`",
        f"- Judge: `{report.get('judge')}`",
        f"- Mode: `{report.get('mode')}`",
        "",
        "## Summary",
        "",
        "| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    overall = (report.get("summary") or {}).get("overall") or {}
    lines.append(summary_row("overall", overall))
    for suite, summary in ((report.get("summary") or {}).get("by_suite") or {}).items():
        lines.append(summary_row(str(suite), summary))
    lines.extend(["", "## Metrics By Suite", ""])
    for suite, summary in ((report.get("summary") or {}).get("by_suite") or {}).items():
        lines.extend([f"### {suite}", "", "| Metric | Value |", "|---|---:|"])
        for key, value in summary.items():
            lines.append(f"| {key} | {value} |")
        lines.append("")
    failures = [item for item in report.get("cases", []) if not item.get("passed")]
    lines.extend(["## Failed Cases", ""])
    if not failures:
        lines.append("No failed cases.")
        return "\n".join(lines)
    for item in failures:
        lines.extend(
            [
                f"### {item.get('suite')} / {item.get('id')}",
                "",
                f"- Question: {item.get('question')}",
                f"- Failure reasons: {', '.join(item.get('failure_reasons') or [])}",
                f"- Retrieved sources: {', '.join(item.get('retrieved_sources') or []) or '(none)'}",
                f"- Tool calls: `{json.dumps(item.get('tool_calls') or [], ensure_ascii=False, default=str)[:1600]}`",
                f"- Task results: `{json.dumps(item.get('task_results') or [], ensure_ascii=False, default=str)[:1600]}`",
                f"- Answer preview: {item.get('answer_preview') or ''}",
                "",
            ]
        )
    return "\n".join(lines)


def summary_row(name: str, summary: dict[str, Any]) -> str:
    return "| {name} | {case_count} | {passed} | {failed} | {pass_rate:.4f} | {avg:.2f} | {p95:.2f} |".format(
        name=name,
        case_count=int(summary.get("case_count") or 0),
        passed=int(summary.get("passed") or 0),
        failed=int(summary.get("failed") or 0),
        pass_rate=float(summary.get("pass_rate") or 0),
        avg=float(summary.get("avg_latency_ms") or 0),
        p95=float(summary.get("p95_latency_ms") or 0),
    )


def print_dry_run(suite_cases: dict[str, list[dict[str, Any]]]) -> None:
    for suite, cases in suite_cases.items():
        for index, case in enumerate(cases, start=1):
            print(f"[dry-run] {suite} #{index} {case.get('id') or case.get('case_id')} role={case.get('role')} question={case.get('question')}")


def run_suite(args: argparse.Namespace) -> int:
    settings = configure_settings(args)
    suite_files = resolve_suite_files(args)
    suite_cases = {
        suite: load_jsonl(path, limit=args.limit, case_id=args.case_id)
        for suite, path in suite_files.items()
        if suite in {"rag", "tool", "e2e"}
    }
    if args.dry_run:
        print_dry_run(suite_cases)
        return 0

    results: list[EvalCaseResult] = []
    runner_cache: dict[str, Any] = {}
    total_cases = sum(len(cases) for cases in suite_cases.values())
    current = 0
    stop_requested = False
    for suite, cases in suite_cases.items():
        if stop_requested:
            break
        for case in cases:
            current += 1
            case_id = str(case.get("id") or case.get("case_id") or f"{suite}_{current:03d}")
            try:
                result, latency_ms = run_case(suite, case, settings, args, runner_cache)
                case_result = evaluate_case(suite, case, result, latency_ms, args, settings)
            except Exception as exc:
                case_result = build_error_result(suite, case, args, exc)
            results.append(case_result)
            status = "pass" if case_result.passed else "fail"
            print(f"[{current}/{total_cases}] {case_id} {status} latency={case_result.latency_ms}ms")
            if args.verbose:
                print(
                    json.dumps(
                        {
                            "route": case_result.route,
                            "tool_calls": case_result.tool_calls,
                            "retrieved_sources": case_result.retrieved_sources,
                            "failures": case_result.failure_reasons,
                        },
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                )
            if case_result.infra_error and getattr(args, "stop_on_infra_error", True):
                print(f"[stop] infra error encountered in {case_id}; stopping remaining cases.")
                stop_requested = True
                break

    report = build_report(args, results)
    json_path = write_json_report(args.output, report)
    md_path = write_markdown_report(args.output, report)
    failures_path = write_failures_jsonl(args.output, results)
    auto_report_path = write_auto_run_report(args, settings, results)
    print("Reports written:")
    print(f"- JSON: {json_path}")
    print(f"- Markdown: {md_path}")
    print(f"- Failures JSONL: {failures_path}")
    print(f"- Auto eval report: {auto_report_path}")
    return 0


def main() -> int:
    args = parse_args()
    return run_suite(args)


if __name__ == "__main__":
    raise SystemExit(main())
