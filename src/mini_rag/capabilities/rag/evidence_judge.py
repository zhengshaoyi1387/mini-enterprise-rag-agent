from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from mini_rag.graph.utils import get_message_content, safe_json_loads


RAG_EVIDENCE_JUDGE_SYSTEM = """
你是企业 RAG Evidence Judge，只输出 JSON。
只评估 current_task_id 的 task_question / rag_task_objective；original_question 仅作背景，retrieval_query 不是回答主题。
只能选择 candidate_sources 中已有 source_id，不得创造证据、扩大问题或要求其他子任务证据。
answerable=true：证据覆盖当前任务核心对象/条件/流程/结论，missing_evidence=[]。
证据不足或只相关但不完整：answerable=false，sufficiency=low，missing_evidence 只写当前任务缺失点。
若候选证据和当前任务相关但不足以完整回答，可把这些候选 source_id 放入 related_source_ids；answerable=false 时 supporting_source_ids 必须为空。
概要问题核心证据足够时可判 medium。
""".strip()


@dataclass(frozen=True)
class EvidenceJudgeDecision:
    answerable: bool = False
    sufficiency: str = "low"
    supporting_source_ids: tuple[str, ...] = ()
    related_source_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "answerable": self.answerable,
            "sufficiency": self.sufficiency,
            "supporting_source_ids": list(self.supporting_source_ids),
            "related_source_ids": list(self.related_source_ids),
            "missing_evidence": list(self.missing_evidence),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SourceWithId:
    source_id: str
    source: dict[str, Any] = field(default_factory=dict)


def source_id_for(src: dict[str, Any], index: int) -> str:
    for key in ("chunk_id", "id", "source_id"):
        value = str(src.get(key) or "").strip()
        if value:
            return value
    source = str(src.get("source") or "").strip()
    rank = str(src.get("rank") or src.get("position") or "").strip()
    if source and rank:
        return f"{source}#rank:{rank}"
    if source:
        return f"{source}#idx:{index}"
    return f"source_{index}"


def attach_source_ids(candidate_sources: list[dict[str, Any]]) -> list[SourceWithId]:
    output: list[SourceWithId] = []
    seen: set[str] = set()
    for idx, src in enumerate(candidate_sources, start=1):
        if not isinstance(src, dict):
            continue
        source_id = source_id_for(src, idx)
        if source_id in seen:
            source_id = f"{source_id}#{idx}"
        seen.add(source_id)
        output.append(SourceWithId(source_id=source_id, source=src))
    return output


def select_sources_by_ids(candidate_sources: list[dict[str, Any]], source_ids: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    wanted = {str(item).strip() for item in (source_ids or []) if str(item).strip()}
    if not wanted:
        return []
    output: list[dict[str, Any]] = []
    for item in attach_source_ids(candidate_sources):
        if item.source_id in wanted:
            output.append(item.source)
    return output


def _compact_candidate_sources(candidate_sources: list[dict[str, Any]], *, max_sources: int = 6, max_preview_chars: int = 650) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in attach_source_ids(candidate_sources)[:max_sources]:
        src = item.source
        preview = str(src.get("text") or src.get("preview") or "")
        if len(preview) > max_preview_chars:
            preview = preview[:max_preview_chars] + "..."
        compact.append(
            {
                "source_id": item.source_id,
                "kb_id": src.get("kb_id"),
                "kb_name": src.get("kb_name"),
                "source": src.get("source"),
                "title_path": src.get("title_path"),
                "preview": preview,
            }
        )
    return compact


def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if value in (None, "", [], {}):
        return ()
    return (str(value).strip(),)


def _append_llm_trace(
    trace_state: dict[str, Any] | None,
    *,
    node: str,
    model_name: str,
    system: str,
    user: str,
    output: str,
    latency_ms: float,
    parsed_output: dict[str, Any] | None,
) -> None:
    if trace_state is None:
        return
    call: dict[str, Any] = {
        "node": node,
        "model": model_name,
        "prompt_chars": len(system) + len(user),
        "output_chars": len(output),
        "latency_ms": latency_ms,
        "json_parse_ok": isinstance(parsed_output, dict),
    }
    # Keep this local and dependency-free. The global TraceBuilder may truncate later.
    call["input"] = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    call["output"] = {"content": output}
    if isinstance(parsed_output, dict):
        call["parsed_output"] = parsed_output
    trace_state.setdefault("llm_calls", []).append(call)


def build_evidence_judge_prompt(
    *,
    original_question: str,
    rag_task_objective: str,
    candidate_sources: list[dict[str, Any]],
    attempt: int,
    current_task_id: str | None = None,
    task_question: str | None = None,
) -> str:
    payload = {
        "original_question": original_question,
        "current_task_id": current_task_id or "",
        "task_question": task_question or rag_task_objective,
        "rag_task_objective": rag_task_objective,
        "attempt": attempt,
        "candidate_sources": _compact_candidate_sources(candidate_sources),
        "output_schema": {
            "answerable": True,
            "sufficiency": "high|medium|low",
            "supporting_source_ids": ["candidate source_id only; empty when answerable=false"],
            "related_source_ids": ["candidate source_id only; optional when answerable=false but related"],
            "missing_evidence": [],
            "reason": "一句话",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def judge_rag_evidence_with_llm(
    *,
    original_question: str,
    rag_task_objective: str,
    candidate_sources: list[dict[str, Any]],
    llm: Any | None,
    attempt: int = 1,
    trace_state: dict[str, Any] | None = None,
    model_name: str = "control_llm",
    current_task_id: str | None = None,
    task_question: str | None = None,
) -> EvidenceJudgeDecision:
    if not candidate_sources:
        return EvidenceJudgeDecision(
            answerable=False,
            sufficiency="low",
            missing_evidence=("没有检索到候选证据",),
            reason="no candidate sources",
        )
    if llm is None:
        return EvidenceJudgeDecision(
            answerable=False,
            sufficiency="low",
            missing_evidence=("缺少 LLM evidence judge，无法可靠判断语义充分性",),
            reason="no llm available for evidence judge",
        )

    user = build_evidence_judge_prompt(
        original_question=original_question,
        rag_task_objective=rag_task_objective,
        candidate_sources=candidate_sources,
        attempt=attempt,
        current_task_id=current_task_id,
        task_question=task_question,
    )
    start = time.perf_counter()
    raw = ""
    parsed: dict[str, Any] | None = None
    try:
        message = llm.invoke([("system", RAG_EVIDENCE_JUDGE_SYSTEM), ("user", user)])
        raw = get_message_content(message)
        loaded = safe_json_loads(raw, default={})
        parsed = loaded if isinstance(loaded, dict) else {}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        _append_llm_trace(
            trace_state,
            node="rag_evidence_judge",
            model_name=model_name,
            system=RAG_EVIDENCE_JUDGE_SYSTEM,
            user=user,
            output=raw or f"ERROR: {exc}",
            latency_ms=latency_ms,
            parsed_output=None,
        )
        return EvidenceJudgeDecision(reason=f"evidence judge failed: {exc}")

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    _append_llm_trace(
        trace_state,
        node="rag_evidence_judge",
        model_name=model_name,
        system=RAG_EVIDENCE_JUDGE_SYSTEM,
        user=user,
        output=raw,
        latency_ms=latency_ms,
        parsed_output=parsed,
    )

    sufficiency = str((parsed or {}).get("sufficiency") or "low").strip().lower()
    if sufficiency not in {"high", "medium", "low"}:
        sufficiency = "low"
    ids = _coerce_str_tuple((parsed or {}).get("supporting_source_ids"))
    related_ids = _coerce_str_tuple((parsed or {}).get("related_source_ids"))
    valid_ids = {item.source_id for item in attach_source_ids(candidate_sources)}
    selected = tuple(source_id for source_id in ids if source_id in valid_ids)
    related = tuple(source_id for source_id in related_ids if source_id in valid_ids)
    missing = _coerce_str_tuple((parsed or {}).get("missing_evidence"))

    raw_answerable = bool((parsed or {}).get("answerable"))
    answerable = raw_answerable and sufficiency in {"high", "medium"} and bool(selected)
    if raw_answerable and not selected:
        missing = missing or ("LLM judge 未选择任何候选 source_id",)
        answerable = False
        sufficiency = "low"

    # Hard structural normalization: only fully answerable judgments may expose
    # supporting_source_ids.  If the LLM returns IDs while answerable=false, keep
    # them as related_source_ids so the final answer can say "未找到完整依据，
    # 但检索到以下相关内容" without treating them as sufficient support.
    if not answerable:
        if not related and selected:
            related = selected
        selected = ()
        sufficiency = "low"

    return EvidenceJudgeDecision(
        answerable=answerable,
        sufficiency=sufficiency,
        supporting_source_ids=selected,
        related_source_ids=related,
        missing_evidence=missing,
        reason=str((parsed or {}).get("reason") or ""),
    )


__all__ = [
    "EvidenceJudgeDecision",
    "RAG_EVIDENCE_JUDGE_SYSTEM",
    "attach_source_ids",
    "build_evidence_judge_prompt",
    "judge_rag_evidence_with_llm",
    "select_sources_by_ids",
    "source_id_for",
]
