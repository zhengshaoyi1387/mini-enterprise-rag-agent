from __future__ import annotations

from typing import Any

from mini_rag.retrieval.retriever import KnowledgeBaseRetriever


def build_knowledge_base_retriever(settings: Any) -> KnowledgeBaseRetriever:
    return KnowledgeBaseRetriever(settings)
