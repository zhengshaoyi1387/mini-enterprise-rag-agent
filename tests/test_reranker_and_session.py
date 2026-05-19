from langchain_core.documents import Document

from mini_rag.config import Settings
from mini_rag.retrieval.reranker import QwenReranker
from mini_rag.retrieval.retriever import KnowledgeBaseRetriever


def test_reranker_falls_back_when_http_call_fails():
    docs = [
        Document(page_content="A", metadata={"chunk_id": "a", "rrf_score": 0.1}),
        Document(page_content="B", metadata={"chunk_id": "b", "rrf_score": 0.2}),
    ]

    def failing_post(*args, **kwargs):
        raise RuntimeError("network down")

    reranker = QwenReranker(
        api_key="test-key",
        model="qwen3-rerank",
        endpoint="https://example.test/reranks",
        http_post=failing_post,
    )
    trace = {}

    ranked = reranker.rerank("query", docs, top_n=2, trace=trace)

    assert [doc.metadata["chunk_id"] for doc in ranked] == ["a", "b"]
    assert trace["rerank_enabled"] is True
    assert "network down" in trace["rerank_error"]


def test_rerank_is_disabled_by_default() -> None:
    settings = Settings(DASHSCOPE_API_KEY="test-key", _env_file=None)

    assert settings.rerank_enabled is False


def test_retriever_auto_disables_rerank_after_endpoint_404(monkeypatch, tmp_path) -> None:
    settings = Settings(
        DASHSCOPE_API_KEY="test-key",
        CHROMA_DIR=tmp_path / "chroma",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=True,
    )

    monkeypatch.setattr("mini_rag.retrieval.retriever.build_qwen_embeddings", lambda _settings: object())
    monkeypatch.setattr("mini_rag.retrieval.retriever.create_vector_store", lambda _settings, _embeddings: object())
    retriever = KnowledgeBaseRetriever(settings)
    docs = [
        Document(page_content="差旅报销材料说明", metadata={"chunk_id": "a", "rank": 1, "rrf_score": 0.9}),
        Document(page_content="会议室使用说明", metadata={"chunk_id": "b", "rank": 2, "rrf_score": 0.8}),
    ]
    monkeypatch.setattr(retriever, "_vector_search", lambda *args, **kwargs: docs)
    monkeypatch.setattr(retriever, "_load_all_documents", lambda kb_ids=None: docs)

    class DisabledReranker:
        def rerank(self, _query, input_docs, top_n, trace):
            trace["rerank_enabled"] = True
            trace["rerank_error"] = "404 Client Error: Not Found for url"
            trace["rerank_http_status"] = 404
            trace["rerank_output_count"] = min(top_n, len(input_docs))
            return input_docs[:top_n]

    retriever._reranker = DisabledReranker()

    _, first_trace = retriever.search("出差报销", enable_rerank=True)
    _, second_trace = retriever.search("出差报销", enable_rerank=True)

    assert first_trace["rerank_fallback"] is True
    assert "404" in first_trace["rerank_warning"]
    assert second_trace["rerank_enabled"] is False
    assert second_trace["rerank_fallback"] is True
