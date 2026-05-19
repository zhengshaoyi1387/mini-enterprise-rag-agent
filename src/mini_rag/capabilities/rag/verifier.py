from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


STOP_TERMS: set[str] = {
    "什么",
    "哪些",
    "怎么",
    "如何",
    "说明",
    "介绍",
    "一下",
    "回来",
    "注意",
    "常见",
    "处理",
    "方式",
    "结合",
    "如果",
    "有没有",
    "当前",
    "公司",
    "企业",
    "知识库",
    "相关",
    "明确",
    "依据",
    "制度",
    "政策",
}

SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("出差", "差旅", "商务旅行", "travel"),
    ("报销", "费用报销", "reimburse", "reimbursement", "expense"),
    ("采购", "procurement", "purchase"),
    ("发票", "票据", "invoice"),
    ("考勤", "迟到", "请假", "缺勤", "attendance"),
    ("请假", "休假", "年假", "leave"),
    ("会议室", "会议室规则", "meeting room", "room booking"),
    ("日程", "会议", "培训", "团建", "calendar", "meeting"),
)

POLICY_MARKERS: tuple[str, ...] = ("制度", "政策", "规则", "规范", "流程", "办法", "要求")


@dataclass(frozen=True)
class RagAnswerabilityReport:
    answerable: bool
    status: str = "answerable"
    message: str = ""
    retrieval_relevance: str = "high"
    answer_sufficiency: str = "high"
    unsupported_task_ids: tuple[str, ...] = ()
    supported_task_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answerable": self.answerable,
            "status": self.status,
            "message": self.message,
            "retrieval_relevance": self.retrieval_relevance,
            "answer_sufficiency": self.answer_sufficiency,
            "unsupported_task_ids": list(self.unsupported_task_ids),
            "supported_task_ids": list(self.supported_task_ids),
            "notes": list(self.notes),
        }


def _source_text(src: dict[str, Any]) -> str:
    return "\n".join(
        str(src.get(key) or "")
        for key in ("source", "kb_id", "kb_name", "title_path", "chunk_id", "preview", "text")
        if src.get(key) not in (None, "", [], {})
    ).lower()


def _task_text(task: dict[str, Any] | None) -> str:
    task = task if isinstance(task, dict) else {}
    return "\n".join(str(task.get(key) or "") for key in ("query", "objective", "purpose", "target_entity")).lower()


def _jieba_terms(text: str) -> set[str]:
    try:
        import jieba  # type: ignore
    except Exception:
        return set()
    return {item.strip().lower() for item in jieba.cut(text) if len(item.strip()) >= 2}


def _cjk_ngrams(text: str) -> set[str]:
    terms: set[str] = set()
    for block in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(block) <= 8:
            terms.add(block)
        for size in (2, 3, 4):
            for index in range(0, max(0, len(block) - size + 1)):
                terms.add(block[index : index + size])
    return terms


def extract_relevance_terms(text: str) -> set[str]:
    text = str(text or "").lower()
    terms = set(re.findall(r"[a-z0-9_+-]{2,}", text))
    terms.update(_jieba_terms(text))
    terms.update(_cjk_ngrams(text))
    return {term for term in terms if term and term not in STOP_TERMS and len(term) >= 2}


def _required_synonym_groups(query_text: str) -> tuple[tuple[str, ...], ...]:
    query_text = str(query_text or "").lower()
    groups: list[tuple[str, ...]] = []
    for group in SYNONYM_GROUPS:
        if any(term.strip().lower() and term.strip().lower() in query_text for term in group):
            groups.append(group)
    return tuple(groups)


def _matches_group(text: str, group: tuple[str, ...]) -> bool:
    text = str(text or "").lower()
    return any(term.strip().lower() and term.strip().lower() in text for term in group)


def _is_short_chinese_policy_query(query_text: str) -> bool:
    text = str(query_text or "").lower()
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]+", text))
    if len(cjk) > 24:
        return False
    return any(marker in text for marker in POLICY_MARKERS)


def _policy_group_supports_source(query_text: str, source_text: str, groups: tuple[tuple[str, ...], ...]) -> bool:
    if not groups or not _is_short_chinese_policy_query(query_text):
        return False
    return all(_matches_group(source_text, group) for group in groups)


class EvidenceRelevanceVerifier:
    """Judge whether a retrieved chunk can support one RAG sub-goal.

    This is a deterministic evidence gate, not a final answer judge. It keeps
    weakly related chunks out of the answer prompt so the LLM cannot turn HR FAQ
    or product examples into unsupported finance-policy answers.
    """

    def __init__(self, *, min_rerank_score: float = 0.5) -> None:
        self.min_rerank_score = float(min_rerank_score)

    def is_supporting_source(self, src: dict[str, Any], task: dict[str, Any] | None = None) -> bool:
        rerank = src.get("rerank_score")
        if rerank is not None:
            try:
                if float(rerank) < self.min_rerank_score:
                    return False
            except Exception:
                pass

        query_text = _task_text(task)
        source_text = _source_text(src)
        if not query_text.strip():
            return True
        if not source_text.strip():
            return False

        required_groups = _required_synonym_groups(query_text)
        if required_groups and not all(_matches_group(source_text, group) for group in required_groups):
            return False
        if _policy_group_supports_source(query_text, source_text, required_groups):
            return True

        query_terms = extract_relevance_terms(query_text)
        source_terms = extract_relevance_terms(source_text)
        if not query_terms:
            return True
        overlap = query_terms & source_terms
        if overlap:
            if len(query_terms) <= 3:
                return True
            return (len(overlap) / max(1, len(query_terms))) >= 0.16 or len(overlap) >= 2

        return bool(src.get("explicit_source_boost"))

    def assess_task_evidence(self, sources: list[dict[str, Any]], task: dict[str, Any] | None = None) -> dict[str, Any]:
        candidates = [src for src in sources if isinstance(src, dict)]
        supporting = [src for src in candidates if self.is_supporting_source(src, task)]
        query_text = _task_text(task)
        candidate_text = "\n".join(_source_text(src) for src in candidates)
        required_groups = _required_synonym_groups(query_text)
        group_match = bool(required_groups) and all(_matches_group(candidate_text, group) for group in required_groups)
        if supporting:
            return {
                "retrieval_relevance": "high",
                "answer_sufficiency": "high" if any(len(str(src.get("preview") or src.get("text") or "")) >= 40 for src in supporting) else "medium",
                "answerable": True,
                "supporting_sources": supporting,
            }
        if candidates and group_match:
            return {
                "retrieval_relevance": "high",
                "answer_sufficiency": "low",
                "answerable": False,
                "supporting_sources": [],
            }
        if candidates:
            return {
                "retrieval_relevance": "low",
                "answer_sufficiency": "low",
                "answerable": False,
                "supporting_sources": [],
            }
        return {
            "retrieval_relevance": "none",
            "answer_sufficiency": "low",
            "answerable": False,
            "supporting_sources": [],
        }


class RagAnswerabilityGate:
    """Decide whether current RAG evidence is sufficient to answer."""

    def __init__(self, verifier: EvidenceRelevanceVerifier | None = None) -> None:
        self.verifier = verifier or EvidenceRelevanceVerifier()

    def evaluate(self, state: dict[str, Any]) -> RagAnswerabilityReport:
        task_results = [item for item in (state.get("task_results") or []) if isinstance(item, dict)]
        rag_results = [item for item in task_results if str(item.get("kind") or "").lower() == "rag"]
        if not rag_results:
            if str(state.get("route") or "") == "rag":
                return RagAnswerabilityReport(
                    answerable=False,
                    status="insufficient_evidence",
                    message="当前可访问知识库未找到明确依据，不能可靠回答该问题。",
                    retrieval_relevance="none",
                    answer_sufficiency="low",
                )
            return RagAnswerabilityReport(answerable=True)

        supported: list[str] = []
        unsupported: list[str] = []
        notes: list[str] = []
        for result in rag_results:
            task_id = str(result.get("task_id") or result.get("query") or "rag")
            sources = [src for src in (result.get("sources") or []) if isinstance(src, dict)]
            judgments = [item for item in (result.get("evidence_judgments") or []) if isinstance(item, dict)]
            latest_judgment = judgments[-1] if judgments else {}
            # New RAG path: sources have already been approved by the LLM evidence judge.
            # Do not re-judge semantic sufficiency with keyword/overlap code here. This gate
            # only enforces that a successful RAG task has explicit supporting sources.
            if sources and bool(latest_judgment.get("answerable", True)):
                supported.append(task_id)
            else:
                unsupported.append(task_id)
                notes.append(str(result.get("unsupported_reason") or "retrieved evidence is weak or missing"))

        if unsupported:
            return RagAnswerabilityReport(
                answerable=False,
                status="insufficient_evidence",
                message="当前可访问知识库未找到明确依据，不能可靠回答该知识库部分。",
                retrieval_relevance="low",
                answer_sufficiency="low",
                unsupported_task_ids=tuple(unsupported),
                supported_task_ids=tuple(supported),
                notes=tuple(notes),
            )
        return RagAnswerabilityReport(answerable=True, supported_task_ids=tuple(supported))


def is_supporting_source(src: dict[str, Any], task: dict[str, Any] | None = None) -> bool:
    return EvidenceRelevanceVerifier().is_supporting_source(src, task)


def answer_has_sources_for_rag(state: dict[str, Any]) -> bool:
    if str(state.get("route") or "") != "rag":
        return True
    answer = str(state.get("final_answer") or "")
    return bool(state.get("sources")) and ("[" in answer or "来源" in answer or "source" in answer.lower())
