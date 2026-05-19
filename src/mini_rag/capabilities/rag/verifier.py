from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RagAnswerabilityReport:
    answerable: bool
    status: str = "answerable"
    mode: str = "full"
    message: str = ""
    retrieval_relevance: str = "high"
    answer_sufficiency: str = "high"
    unsupported_task_ids: tuple[str, ...] = ()
    supported_task_ids: tuple[str, ...] = ()
    related_task_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answerable": self.answerable,
            "status": self.status,
            "mode": self.mode,
            "message": self.message,
            "retrieval_relevance": self.retrieval_relevance,
            "answer_sufficiency": self.answer_sufficiency,
            "unsupported_task_ids": list(self.unsupported_task_ids),
            "supported_task_ids": list(self.supported_task_ids),
            "related_task_ids": list(self.related_task_ids),
            "notes": list(self.notes),
        }


class RagAnswerabilityGate:
    """Structural gate for the current LLM-judged RAG path.

    Semantic relevance belongs to ``evidence_judge.py``. This gate deliberately
    does not re-score sources with keywords, synonyms, or policy markers. It
    only enforces the answer-facing contract: answer with LLM-approved
    supporting sources, keep candidate sources as debug data, and aggregate
    multi-task RAG per task instead of using one unsupported task to block all
    supported work.
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
        related: list[str] = []
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
            if any(isinstance(src, dict) for src in (result.get("related_sources") or [])):
                related.append(task_id)
            notes.append(str(result.get("unsupported_reason") or latest_judgment.get("reason") or "supporting evidence is missing"))

        if supported and unsupported:
            return RagAnswerabilityReport(
                answerable=True,
                status="partial_evidence",
                mode="partial",
                message="部分子问题缺少明确依据，已回答有证据支持的部分。",
                retrieval_relevance="partial",
                answer_sufficiency="partial",
                unsupported_task_ids=tuple(unsupported),
                supported_task_ids=tuple(supported),
                related_task_ids=tuple(related),
                notes=tuple(notes),
            )
        if supported:
            return RagAnswerabilityReport(answerable=True, mode="full", supported_task_ids=tuple(supported))

        if related:
            return RagAnswerabilityReport(
                answerable=True,
                status="related_evidence",
                mode="partial",
                message="当前可访问知识库未找到完整明确依据，但检索到相关内容，可作为相关参考谨慎说明。",
                retrieval_relevance="partial",
                answer_sufficiency="partial",
                unsupported_task_ids=tuple(unsupported),
                related_task_ids=tuple(related),
                notes=tuple(notes),
            )

        has_non_rag_success = any(
            str(item.get("kind") or "").lower() != "rag"
            and str(item.get("status") or "").lower() in {"ok", "success"}
            for item in task_results
        )
        if has_non_rag_success:
            return RagAnswerabilityReport(
                answerable=True,
                status="partial_evidence",
                mode="partial",
                message="知识库子问题缺少明确依据，但已保留其他已完成任务结果。",
                retrieval_relevance="none",
                answer_sufficiency="partial",
                unsupported_task_ids=tuple(unsupported),
                related_task_ids=tuple(related),
                notes=tuple(notes),
            )

        return RagAnswerabilityReport(
            answerable=False,
            status="insufficient_evidence",
            mode="none",
            message="当前可访问知识库未找到明确依据，不能可靠回答该知识库部分。",
            retrieval_relevance="none",
            answer_sufficiency="low",
            unsupported_task_ids=tuple(unsupported),
            notes=tuple(notes),
        )


def _insufficient(task_id: str, message: str) -> RagAnswerabilityReport:
    return RagAnswerabilityReport(
        answerable=False,
        status="insufficient_evidence",
        mode="none",
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
