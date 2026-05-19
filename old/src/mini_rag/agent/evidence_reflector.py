from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.documents import Document

from mini_rag.agent.llm_json import message_content, parse_json_object
from mini_rag.prompts import EVIDENCE_REFLECTOR_SYSTEM_PROMPT, format_evidence_reflector_user_prompt
from mini_rag.rag.citation import format_documents_as_evidence


@dataclass
class EvidenceAssessment:
    """证据评估节点的结构化输出。"""

    is_sufficient: bool
    reason: str
    missing_information: list[str] = field(default_factory=list)
    followup_queries: list[str] = field(default_factory=list)
    can_answer_partial: bool = False
    raw_response: str = ""
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return {
            "is_sufficient": self.is_sufficient,
            "reason": self.reason,
            "missing_information": self.missing_information,
            "followup_queries": self.followup_queries,
            "can_answer_partial": self.can_answer_partial,
            "fallback_used": self.fallback_used,
        }


def assess_evidence(
    llm,
    question: str,
    standalone_query: str,
    docs: list[Document],
    retrieval_queries: list[str],
) -> EvidenceAssessment:
    """让 LLM 判断当前证据是否足够回答。

    这个节点解决“检索到了相关内容，但不一定足够回答”的问题。
    例如用户问三个模块，但证据只覆盖一个模块，此时 LLM 应该要求继续检索，
    或者最终回答时明确证据不足。
    """
    evidence_text = format_documents_as_evidence(docs)
    messages = [
        {"role": "system", "content": EVIDENCE_REFLECTOR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": format_evidence_reflector_user_prompt(
                question,
                standalone_query,
                retrieval_queries,
                evidence_text,
            ),
        },
    ]
    raw = message_content(llm.invoke(messages))
    payload = parse_json_object(raw)
    if not payload:
        return fallback_assessment(bool(docs), raw)

    followups = normalize_string_list(payload.get("followup_queries"), max_items=3)
    return EvidenceAssessment(
        is_sufficient=bool(payload.get("is_sufficient", False)),
        reason=str(payload.get("reason") or "LLM evidence assessment"),
        missing_information=normalize_string_list(payload.get("missing_information"), max_items=6),
        followup_queries=followups,
        can_answer_partial=bool(payload.get("can_answer_partial", False)),
        raw_response=raw,
        fallback_used=False,
    )


def fallback_assessment(has_docs: bool, raw: str = "") -> EvidenceAssessment:
    """证据评估 JSON 失败时的兜底。

    有证据时保守允许进入 final；没有证据时标记不足。
    """
    return EvidenceAssessment(
        is_sufficient=has_docs,
        reason="证据评估 JSON 解析失败，使用保守 fallback。",
        missing_information=[] if has_docs else ["未检索到证据"],
        followup_queries=[],
        can_answer_partial=has_docs,
        raw_response=raw,
        fallback_used=True,
    )


def normalize_string_list(value, max_items: int) -> list[str]:
    """清洗 LLM 输出的字符串列表。"""
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for raw_item in value:
        item = str(raw_item).strip()
        if item and item not in items:
            items.append(item)
        if len(items) >= max_items:
            break
    return items
