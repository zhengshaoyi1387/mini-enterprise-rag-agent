from __future__ import annotations

import time
from typing import Any

from mini_rag.capabilities.rag.evidence_judge import source_id_for
from mini_rag.skills.executor import SkillExecutor, permission_tokens_from_runtime_context
from mini_rag.skills.registry import SkillRegistry


POLICY_GAP_SKILL_NAME = "policy_gap_checker"


def infer_required_slots_for_policy_gap(task_question: str) -> list[str]:
    text = str(task_question or "")
    slots: list[str] = []
    if any(token in text for token in ("是否", "能否", "可不可以", "可以", "允许", "报销吗")):
        slots.extend(["是否允许", "适用条件", "明确政策条款"])
    if any(token in text for token in ("流程", "怎么办", "怎么申请", "步骤")):
        slots.extend(["申请入口或发起方式", "审批流程", "所需材料", "提交或处理时限"])
    if any(token in text for token in ("材料", "凭证", "发票")):
        slots.extend(["所需材料", "凭证要求"])
    if not slots:
        slots.extend(["核心结论", "适用条件", "操作要求"])
    output: list[str] = []
    for slot in slots:
        if slot not in output:
            output.append(slot)
    return output


def should_run_policy_gap_checker(task_result: dict[str, Any], task: dict[str, Any], runtime_context: dict[str, Any]) -> tuple[bool, str]:
    if str(task_result.get("kind") or "").lower() != "rag":
        return False, "not_rag_task"
    if str(task_result.get("status") or "").lower() == "ok":
        return False, "answerable"
    related_sources = task_result.get("related_sources") if isinstance(task_result.get("related_sources"), list) else []
    related_summary = str(task_result.get("related_evidence_summary") or "")
    if not related_sources and not related_summary:
        return False, "no_related_evidence"
    text = " ".join(
        str(value or "")
        for value in (
            task.get("objective"),
            task.get("query"),
            task.get("rag_query"),
            task_result.get("objective"),
            task_result.get("query"),
        )
    )
    if not any(token in text for token in ("政策", "制度", "流程", "是否", "允许", "可以", "能否", "材料", "审批", "报销")):
        return False, "not_policy_gap_question"
    if "rag:read" not in permission_tokens_from_runtime_context(runtime_context):
        return False, "permission_missing"
    return True, "unsupported_rag_with_related_policy_evidence"


def build_policy_gap_arguments(task_result: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    question = str(
        task.get("query")
        or task.get("rag_query")
        or task.get("objective")
        or task_result.get("query")
        or task_result.get("objective")
        or ""
    ).strip()
    related_sources = [src for src in (task_result.get("related_sources") or []) if isinstance(src, dict)]
    evidence_items: list[dict[str, Any]] = []
    for index, src in enumerate(related_sources, start=1):
        evidence_items.append(
            {
                "source_id": source_id_for(src, index),
                "title": src.get("title_path") or src.get("source") or "",
                "content": src.get("text") or src.get("preview") or "",
            }
        )
    return {
        "question": question,
        "evidence_items": evidence_items,
        "required_slots": infer_required_slots_for_policy_gap(question),
    }


def run_policy_gap_checker_for_task(
    *,
    task_result: dict[str, Any],
    task: dict[str, Any],
    runtime_context: dict[str, Any],
    registry: SkillRegistry,
    executor: SkillExecutor | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    manifest = registry.get_skill(POLICY_GAP_SKILL_NAME)
    if manifest is None:
        return {
            "ok": False,
            "skill_name": POLICY_GAP_SKILL_NAME,
            "error": {"type": "skill_unavailable", "message": "policy_gap_checker skill is not registered"},
            "trace": {"latency_ms": round((time.perf_counter() - started) * 1000, 2)},
        }
    arguments = build_policy_gap_arguments(task_result, task)
    result = (executor or SkillExecutor(registry)).execute(
        {
            "skill_name": POLICY_GAP_SKILL_NAME,
            "arguments": arguments,
            "runtime_context": runtime_context,
        }
    )
    trace = dict(result.get("trace") or {})
    trace.update(
        {
            "trigger_reason": "unsupported_rag_with_related_policy_evidence",
            "evidence_items_count": len(arguments.get("evidence_items") or []),
            "required_slots_count": len(arguments.get("required_slots") or []),
            "latency_ms": trace.get("latency_ms", round((time.perf_counter() - started) * 1000, 2)),
        }
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "skill_name": POLICY_GAP_SKILL_NAME,
            "error": result.get("error") or {"type": "execution_error", "message": "policy_gap_checker failed"},
            "trace": trace,
        }
    payload = result.get("result") if isinstance(result.get("result"), dict) else {}
    trace["covered_slots_count"] = len(payload.get("covered_slots") or [])
    trace["partial_slots_count"] = len(payload.get("partial_slots") or [])
    trace["missing_slots_count"] = len(payload.get("missing_slots") or [])
    return {
        "ok": True,
        "skill_name": POLICY_GAP_SKILL_NAME,
        "covered_slots": payload.get("covered_slots") or [],
        "partial_slots": payload.get("partial_slots") or [],
        "missing_slots": payload.get("missing_slots") or [],
        "overall": payload.get("overall"),
        "limitations": payload.get("limitations") or [],
        "trace": trace,
    }


__all__ = [
    "POLICY_GAP_SKILL_NAME",
    "build_policy_gap_arguments",
    "infer_required_slots_for_policy_gap",
    "run_policy_gap_checker_for_task",
    "should_run_policy_gap_checker",
]
