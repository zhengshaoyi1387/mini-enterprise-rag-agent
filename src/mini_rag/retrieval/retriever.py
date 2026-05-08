from __future__ import annotations

from langchain_core.documents import Document

from mini_rag.config import Settings
from mini_rag.ingestion.kb_config import normalize_kb_ids
from mini_rag.models.qwen import build_qwen_embeddings
from mini_rag.observability.timer import Timer
from mini_rag.retrieval.hybrid import bm25_rank, reciprocal_rank_fusion
from mini_rag.retrieval.reranker import QwenReranker
from mini_rag.retrieval.vector_store import create_vector_store


class KnowledgeBaseRetriever:
    """Enterprise knowledge-base retriever.

    The retriever supports knowledge-base-level filtering through ``kb_ids``.
    Permission is *not* configured per chunk; each chunk only stores its owning
    ``kb_id``. The API/graph computes allowed_kbs first and passes them here so
    unauthorized documents are never retrieved into the model context.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.embeddings = build_qwen_embeddings(settings)
        self.vector_store = create_vector_store(settings, self.embeddings)
        self._corpus_cache: list[Document] | None = None
        self._reranker: QwenReranker | None = None

    def search(
        self,
        query: str,
        top_k: int | None = None,
        candidate_k: int | None = None,
        retrieval_mode: str | None = None,
        enable_rerank: bool | None = None,
        kb_ids: list[str] | None = None,
    ) -> tuple[list[Document], dict]:
        """Search documents within allowed knowledge bases.

        ``kb_ids`` should already be permission-filtered by the LangGraph
        permission node. Passing an empty list means no accessible KB and returns
        no results; passing None means legacy behavior with no KB filter.
        """

        top_k = top_k or self.settings.top_k
        candidate_k = candidate_k or self.settings.candidate_k
        retrieval_mode = retrieval_mode or self.settings.retrieval_mode
        enable_rerank = self.settings.rerank_enabled if enable_rerank is None else enable_rerank
        normalized_kbs = normalize_kb_ids(kb_ids) if kb_ids is not None else None
        trace: dict = {
            "query": query,
            "top_k": top_k,
            "candidate_k": candidate_k,
            "retrieval_engine": retrieval_mode,
            "kb_ids": normalized_kbs,
            "permission_filter_applied": normalized_kbs is not None,
        }

        if normalized_kbs == []:
            trace["result_count"] = 0
            trace["results"] = []
            return [], trace

        with Timer(trace, "retrieval"):
            if retrieval_mode == "vector":
                docs = self._vector_search(query, top_k=top_k, candidate_k=candidate_k, kb_ids=normalized_kbs)
            else:
                docs = self._hybrid_search(
                    query,
                    top_k=top_k,
                    candidate_k=candidate_k,
                    enable_rerank=enable_rerank,
                    trace=trace,
                    kb_ids=normalized_kbs,
                )

        trace["result_count"] = len(docs)
        trace["results"] = [document_to_trace_item(doc) for doc in docs]
        return docs, trace

    def _vector_search(self, query: str, top_k: int, candidate_k: int, kb_ids: list[str] | None = None) -> list[Document]:
        scored_results = self._similarity_search_with_kb_filter(query, k=candidate_k, kb_ids=kb_ids)

        docs: list[Document] = []
        for rank, (doc, score) in enumerate(scored_results[:top_k], start=1):
            metadata = dict(doc.metadata or {})
            metadata.update(
                {
                    "rank": rank,
                    "vector_score": float(score),
                    "retrieval_channel": "chroma_vector",
                }
            )
            docs.append(Document(page_content=doc.page_content, metadata=metadata))
        return docs

    def _similarity_search_with_kb_filter(self, query: str, k: int, kb_ids: list[str] | None) -> list[tuple[Document, float]]:
        """Run Chroma vector search with metadata filter before retrieval.

        Different LangChain/Chroma versions vary in filter syntax. For multiple
        KBs we first try ``$in``; if unsupported, we query each allowed KB with an
        equality filter and merge results. This still enforces filtering before
        documents enter the RAG context.
        """

        if kb_ids is None:
            return self.vector_store.similarity_search_with_score(query, k=k)
        if not kb_ids:
            return []
        if len(kb_ids) == 1:
            return self.vector_store.similarity_search_with_score(query, k=k, filter={"kb_id": kb_ids[0]})
        try:
            return self.vector_store.similarity_search_with_score(query, k=k, filter={"kb_id": {"$in": kb_ids}})
        except Exception:
            merged: list[tuple[Document, float]] = []
            per_k = max(k, 1)
            for kb_id in kb_ids:
                merged.extend(self.vector_store.similarity_search_with_score(query, k=per_k, filter={"kb_id": kb_id}))
            merged.sort(key=lambda item: float(item[1]))
            return merged[:k]

    def _hybrid_search(
        self,
        query: str,
        top_k: int,
        candidate_k: int,
        enable_rerank: bool,
        trace: dict,
        kb_ids: list[str] | None = None,
    ) -> list[Document]:
        vector_docs = self._vector_search(query, top_k=candidate_k, candidate_k=candidate_k, kb_ids=kb_ids)
        corpus_docs = self._load_all_documents(kb_ids=kb_ids)
        bm25_results = bm25_rank(query, corpus_docs, top_k=candidate_k)
        trace["vector_candidate_count"] = len(vector_docs)
        trace["bm25_candidate_count"] = len(bm25_results)

        doc_by_id: dict[str, Document] = {}
        vector_channel: list[tuple[str, float]] = []
        for doc in vector_docs:
            chunk_id = doc.metadata.get("chunk_id")
            if chunk_id:
                doc_by_id[str(chunk_id)] = doc
                vector_channel.append((str(chunk_id), float(doc.metadata.get("vector_score", 0.0))))

        bm25_channel: list[tuple[str, float]] = []
        for rank, (doc, score) in enumerate(bm25_results, start=1):
            chunk_id = doc.metadata.get("chunk_id")
            if not chunk_id:
                continue
            metadata = dict(doc.metadata or {})
            metadata.update({"bm25_rank": rank, "bm25_score": float(score)})
            doc_by_id[str(chunk_id)] = Document(page_content=doc.page_content, metadata=metadata)
            bm25_channel.append((str(chunk_id), float(score)))

        fused = reciprocal_rank_fusion([vector_channel, bm25_channel], k=self.settings.rrf_k)
        trace["rrf_candidate_count"] = len(fused)
        fused_docs: list[Document] = []
        for rank, (chunk_id, rrf_score) in enumerate(fused, start=1):
            doc = doc_by_id[chunk_id]
            metadata = dict(doc.metadata or {})
            metadata.update({"rank": rank, "rrf_score": rrf_score, "retrieval_channel": "hybrid_rrf"})
            fused_docs.append(Document(page_content=doc.page_content, metadata=metadata))

        if enable_rerank:
            if self._reranker is None:
                self._reranker = QwenReranker(
                    api_key=self.settings.require_api_key(),
                    model=self.settings.qwen_rerank_model,
                    endpoint=self.settings.qwen_rerank_endpoint,
                )
            return self._reranker.rerank(query, fused_docs, top_n=min(self.settings.rerank_top_n, top_k), trace=trace)

        trace["rerank_enabled"] = False
        return fused_docs[:top_k]

    def _load_all_documents(self, kb_ids: list[str] | None = None) -> list[Document]:
        if self._corpus_cache is None:
            payload = self.vector_store.get(include=["documents", "metadatas"])
            docs: list[Document] = []
            for content, metadata in zip(payload.get("documents", []), payload.get("metadatas", [])):
                if content:
                    docs.append(Document(page_content=content, metadata=metadata or {}))
            self._corpus_cache = docs
        if kb_ids is None:
            return list(self._corpus_cache)
        allowed = set(kb_ids)
        return [doc for doc in self._corpus_cache if doc.metadata.get("kb_id") in allowed]


def document_to_trace_item(doc: Document) -> dict:
    md = doc.metadata or {}
    return {
        "rank": md.get("rank"),
        "source": md.get("source"),
        "kb_id": md.get("kb_id"),
        "kb_name": md.get("kb_name"),
        "title_path": md.get("title_path"),
        "chunk_id": md.get("chunk_id"),
        "vector_score": md.get("vector_score"),
        "bm25_score": md.get("bm25_score"),
        "rrf_score": md.get("rrf_score"),
        "rerank_score": md.get("rerank_score"),
        "preview": doc.page_content[:160],
    }
