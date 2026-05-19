from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from mini_rag.graph.utils import get_message_content, safe_json_loads


RAG_REFLECT_SYSTEM = """
你是企业 RAG 检索自修复器。你不是在改写用户问题，只能生成下一次检索用的 retrieval_query。

硬规则：
- original_question / rag_task_objective 是最终回答主题，retrieval_query 仅用于检索。
- retrieval_query 必须保持 same_topic，不得扩大用户问题范围，不得加入用户没有问的新主题。
- 只能围绕 missing_evidence 补充检索表达；如果无法在同一问题范围内补检索，should_retry=false。
- target_kbs 必须从 allowed_kbs 中选择，不得请求未授权知识库。
- 不得输出最终回答，不得解释制度内容。
- 只输出 JSON。
""".strip()


@dataclass(frozen=True)
class RagRetryDecision:
    should_retry: bool = False
    reason: str = ""
    retrieval_query: str | None = None
    target_kbs: tuple[str, ...] = ()
    query_scope: str = "invalid"
    expected_evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_retry": self.should_retry,
            "reason": self.reason,
            "retrieval_query": self.retrieval_query,
            "target_kbs": list(self.target_kbs),
            "query_scope": self.query_scope,
            "expected_evidence": list(self.expected_evidence),
        }


def _coerce_str_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if value in (None, "", [], {}):
        return ()
    return (str(value).strip(),)


def validate_retrieval_query(
    original_query: str,
    retrieval_query: str | None,
    target_kbs: list[str] | tuple[str, ...] | None,
    allowed_kbs: list[str] | tuple[str, ...] | None,
    candidate_sources: list[dict[str, Any]] | None,
    *,
    query_scope: str = "same_topic",
) -> bool:
    """Validate only hard boundaries, not semantic relevance.

    Semantic same-topic judgment is intentionally handled by the LLM reflect prompt
    and the LLM evidence judge. This function avoids keyword/synonym rules and only
    enforces deterministic guardrails: non-empty query, bounded length, same_topic
    declaration, and authorized KB scope.
    """
    del original_query, candidate_sources
    query = str(retrieval_query or "").strip()
    if not query or str(query_scope or "").strip() != "same_topic":
        return False
    if len(query) > 180:
        return False
    targets = {str(kb).strip() for kb in (target_kbs or []) if str(kb).strip()}
    allowed = {str(kb).strip() for kb in (allowed_kbs or []) if str(kb).strip()}
    if targets and allowed and not targets.issubset(allowed):
        return False
    return True


def _compact_candidate_titles(candidate_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": src.get("source"),
            "kb_id": src.get("kb_id"),
            "title_path": src.get("title_path"),
        }
        for src in candidate_sources[:5]
        if isinstance(src, dict)
    ]


def _build_reflect_prompt(
    *,
    question: str,
    task: dict[str, Any],
    initial_query: str,
    candidate_sources: list[dict[str, Any]],
    unsupported_reason: str,
    missing_evidence: list[str] | tuple[str, ...],
    allowed_kbs: list[str],
) -> str:
    payload = {
        "original_question": question,
        "rag_task_objective": task.get("objective") or task.get("query") or initial_query,
        "initial_query": initial_query,
        "unsupported_reason": unsupported_reason,
        "missing_evidence": list(missing_evidence or []),
        "allowed_kbs": allowed_kbs,
        "candidate_titles": _compact_candidate_titles(candidate_sources),
        "output_schema": {
            "should_retry": True,
            "reason": "为什么仍可在同一问题范围内补检索",
            "retrieval_query": "只用于检索的同主题查询",
            "target_kbs": ["allowed kb id only"],
            "query_scope": "same_topic",
            "expected_evidence": ["要补齐的证据点"],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


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
        "input": {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        "output": {"content": output},
    }
    if isinstance(parsed_output, dict):
        call["parsed_output"] = parsed_output
    trace_state.setdefault("llm_calls", []).append(call)


def maybe_rewrite_rag_query(
    *,
    question: str,
    task: dict[str, Any],
    initial_query: str,
    candidate_sources: list[dict[str, Any]],
    unsupported_reason: str,
    allowed_kbs: list[str],
    llm: Any | None,
    missing_evidence: list[str] | tuple[str, ...] | None = None,
    trace_state: dict[str, Any] | None = None,
    model_name: str = "control_llm",
) -> RagRetryDecision:
    if llm is None:
        return RagRetryDecision(reason="no llm available for rag reflect")
    prompt = _build_reflect_prompt(
        question=question,
        task=task,
        initial_query=initial_query,
        candidate_sources=candidate_sources,
        unsupported_reason=unsupported_reason,
        missing_evidence=missing_evidence or [],
        allowed_kbs=allowed_kbs,
    )
    raw = ""
    parsed: dict[str, Any] | None = None
    start = time.perf_counter()
    try:
        raw_message = llm.invoke([("system", RAG_REFLECT_SYSTEM), ("user", prompt)])
        raw = get_message_content(raw_message)
        loaded = safe_json_loads(raw, default={})
        parsed = loaded if isinstance(loaded, dict) else {}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        _append_llm_trace(
            trace_state,
            node="rag_reflect",
            model_name=model_name,
            system=RAG_REFLECT_SYSTEM,
            user=prompt,
            output=raw or f"ERROR: {exc}",
            latency_ms=latency_ms,
            parsed_output=None,
        )
        return RagRetryDecision(reason=f"rag reflect failed: {exc}")
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    _append_llm_trace(
        trace_state,
        node="rag_reflect",
        model_name=model_name,
        system=RAG_REFLECT_SYSTEM,
        user=prompt,
        output=raw,
        latency_ms=latency_ms,
        parsed_output=parsed,
    )
    if not isinstance(parsed, dict) or not bool(parsed.get("should_retry")):
        return RagRetryDecision(reason=str((parsed or {}).get("reason") or "rag reflect chose not to retry"))
    retrieval_query = str(parsed.get("retrieval_query") or "").strip()
    target_kbs = _coerce_str_list(parsed.get("target_kbs"))
    query_scope = str(parsed.get("query_scope") or "invalid").strip()
    expected = _coerce_str_list(parsed.get("expected_evidence"))
    if not validate_retrieval_query(
        original_query=initial_query,
        retrieval_query=retrieval_query,
        target_kbs=target_kbs,
        allowed_kbs=allowed_kbs,
        candidate_sources=candidate_sources,
        query_scope=query_scope,
    ):
        return RagRetryDecision(
            should_retry=False,
            reason=f"invalid retrieval_query: {parsed.get('reason') or ''}".strip(),
            retrieval_query=retrieval_query or None,
            target_kbs=target_kbs,
            query_scope=query_scope,
            expected_evidence=expected,
        )
    return RagRetryDecision(
        should_retry=True,
        reason=str(parsed.get("reason") or "retry with validated same-topic retrieval query"),
        retrieval_query=retrieval_query,
        target_kbs=target_kbs,
        query_scope=query_scope,
        expected_evidence=expected,
    )


__all__ = ["RAG_REFLECT_SYSTEM", "RagRetryDecision", "maybe_rewrite_rag_query", "validate_retrieval_query"]
