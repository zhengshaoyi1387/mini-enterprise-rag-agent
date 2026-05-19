from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


class RagAnswerabilityGate:
    """Structural gate for the current LLM-judged RAG path.

    Semantic relevance belongs to ``evidence_judge.py``. This gate deliberately
    does not re-score sources with keywords, synonyms, or policy markers. It
    only enforces the answer-facing contract: each RAG task needs supporting
    sources approved by the LLM judge; candidate sources are debug data only.
    """

    def evaluate(self, state: dict[str, Any]) -> RagAnswerabilityReport:
        task_results = [item for item in (state.get("task_results") or []) if isinstance(item, dict)]
        rag_results = [item for item in task_results if str(item.get("kind") or "").lower() == "rag"]
        if not rag_results:
            if str(state.get("route") or "") == "rag":
                return _insufficient("rag", "当前可访问知识库未找到明确依据，不能可靠回答该问题。")
            return RagAnswerabilityReport(answerable=True)

        supported: list[str] = []
        unsupported: list[str] = []
        notes: list[str] = []
        for result in rag_results:
            task_id = str(result.get("task_id") or result.get("query") or "rag")
            sources = [src for src in (result.get("sources") or []) if isinstance(src, dict)]
            judgments = [item for item in (result.get("evidence_judgments") or []) if isinstance(item, dict)]
            latest_judgment = judgments[-1] if judgments else {}
            judge_allows = bool(latest_judgment.get("answerable", bool(sources)))
            if sources and judge_allows:
                supported.append(task_id)
                continue
            unsupported.append(task_id)
            notes.append(str(result.get("unsupported_reason") or latest_judgment.get("reason") or "supporting evidence is missing"))

        if unsupported:
            return RagAnswerabilityReport(
                answerable=False,
                status="insufficient_evidence",
                message="当前可访问知识库未找到明确依据，不能可靠回答该知识库部分。",
                retrieval_relevance="unknown",
                answer_sufficiency="low",
                unsupported_task_ids=tuple(unsupported),
                supported_task_ids=tuple(supported),
                notes=tuple(notes),
            )
        return RagAnswerabilityReport(answerable=True, supported_task_ids=tuple(supported))


def _insufficient(task_id: str, message: str) -> RagAnswerabilityReport:
    return RagAnswerabilityReport(
        answerable=False,
        status="insufficient_evidence",
        message=message,
        retrieval_relevance="none",
        answer_sufficiency="low",
        unsupported_task_ids=(task_id,),
    )


def answer_has_sources_for_rag(state: dict[str, Any]) -> bool:
    if str(state.get("route") or "") != "rag":
        return True
    answer = str(state.get("final_answer") or "")
    return bool(state.get("sources")) and ("[" in answer or "来源" in answer or "source" in answer.lower())
