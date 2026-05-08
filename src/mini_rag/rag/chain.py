from __future__ import annotations

from mini_rag.config import Settings
from mini_rag.models.qwen import build_qwen_chat_model
from mini_rag.observability.timer import Timer
from mini_rag.prompts import format_final_user_prompt
from mini_rag.rag.citation import format_documents_as_evidence, format_sources
from mini_rag.rag.prompt import RAG_SYSTEM_PROMPT
from mini_rag.retrieval.retriever import KnowledgeBaseRetriever


class RAGQuestionAnswerer:
    """不经过 Agent 的普通 RAG 问答器。

    为什么保留这个类？
    - Agent 出问题时，可以用普通 RAG Chain 排查是不是检索或 prompt 的问题。
    - 面试时也可以说明你把 RAG 能力和 Agent 编排解耦了。
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.retriever = KnowledgeBaseRetriever(settings)
        self.llm = build_qwen_chat_model(settings)

    def ask(
        self,
        question: str,
        retrieval_mode: str | None = None,
        enable_rerank: bool | None = None,
    ) -> dict:
        trace: dict = {"mode": "rag_chain", "question": question}

        docs, retrieval_trace = self.retriever.search(
            question,
            retrieval_mode=retrieval_mode,
            enable_rerank=enable_rerank,
        )
        trace["retrieval"] = retrieval_trace

        evidence_text = format_documents_as_evidence(docs)
        user_prompt = format_final_user_prompt(
            question=question,
            standalone_query=question,
            summary="",
            evidence_assessment=None,
            evidence_text=evidence_text,
        )

        with Timer(trace, "llm"):
            response = self.llm.invoke(
                [
                    {"role": "system", "content": RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )

        answer = response.content
        trace["answer"] = answer
        trace["sources"] = format_sources(docs)

        return {
            "answer": answer,
            "sources": format_sources(docs),
            "trace": trace,
        }
