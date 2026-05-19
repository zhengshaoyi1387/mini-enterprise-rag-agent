from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from mini_rag.graph.utils import get_message_content, safe_json_loads


RAG_EVIDENCE_JUDGE_SYSTEM = """
你是企业 RAG 的证据审查器，不回答用户，只判断候选证据是否足够回答原问题。

硬规则：
- 判断对象只能是 original_question / rag_task_objective，不得把 retrieval_query 当成问题主题。
- 不要因为候选证据“看起来相关”就判定充分；必须检查它是否覆盖用户问题的关键约束、对象、流程、条件、金额、时间、例外或结论。
- 只能从 candidate_sources 中选择 supporting_source_ids，不得创造证据，不得选择不存在的 source_id。
- 如果证据只相关但不完整，answerable=false 或 sufficiency=low，并写出 missing_evidence。
- missing_evidence 必须和 reason 保持一致。
- 如果 reason 中提到“缺少”“不足”“未覆盖”“没有说明”某些信息，必须把这些信息逐项写入 missing_evidence。
- 如果 answerable=true 且 missing_evidence=[]，reason 只能说明“当前证据足以回答用户当前问题”，不要再说缺少其他内容。
- 对概要型问题，如果证据足以做概要介绍但不足以展开完整细节，可以判 answerable=true、sufficiency=medium、missing_evidence=[]；reason 应表述为“足以回答概要问题，但不支持进一步展开未被用户要求的细节”。
- 不要因为候选证据没有覆盖用户未要求的细节，就把它写成缺失证据。
- 如果问题只是概要介绍，证据覆盖核心主题即可 sufficiency=medium/high；如果问题询问具体金额、材料、审批节点、日期、责任人或例外，则必须覆盖这些要点才可 answerable=true。
- 不得扩大用户问题范围，不得要求检索用户没有问的新主题。
- 只输出 JSON，不要输出自然语言解释。
""".strip()


@dataclass(frozen=True)
class EvidenceJudgeDecision:
    answerable: bool = False
    sufficiency: str = "low"
    supporting_source_ids: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "answerable": self.answerable,
            "sufficiency": self.sufficiency,
            "supporting_source_ids": list(self.supporting_source_ids),
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


def _compact_candidate_sources(candidate_sources: list[dict[str, Any]], *, max_sources: int = 8, max_preview_chars: int = 900) -> list[dict[str, Any]]:
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
) -> str:
    payload = {
        "original_question": original_question,
        "rag_task_objective": rag_task_objective,
        "attempt": attempt,
        "candidate_sources": _compact_candidate_sources(candidate_sources),
        "output_schema": {
            "answerable": True,
            "sufficiency": "high | medium | low",
            "supporting_source_ids": ["source_id from candidate_sources only"],
            "missing_evidence": ["缺失的关键证据，若无则为空数组"],
            "reason": "一句话说明判断依据",
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
    valid_ids = {item.source_id for item in attach_source_ids(candidate_sources)}
    selected = tuple(source_id for source_id in ids if source_id in valid_ids)
    missing = _coerce_str_tuple((parsed or {}).get("missing_evidence"))
    answerable = bool((parsed or {}).get("answerable")) and sufficiency in {"high", "medium"} and bool(selected)
    if bool((parsed or {}).get("answerable")) and not selected:
        missing = missing or ("LLM judge 未选择任何候选 source_id",)
        answerable = False
        sufficiency = "low"
    return EvidenceJudgeDecision(
        answerable=answerable,
        sufficiency=sufficiency,
        supporting_source_ids=selected,
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
