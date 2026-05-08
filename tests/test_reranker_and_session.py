from langchain_core.documents import Document

from mini_rag.agent.session import InMemorySessionStore
from mini_rag.retrieval.reranker import QwenReranker


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


def test_session_store_keeps_recent_turns_only():
    store = InMemorySessionStore(max_turns=2)

    store.append_turn("s1", "q1", "a1")
    store.append_turn("s1", "q2", "a2")
    store.append_turn("s1", "q3", "a3")

    history = store.get_history("s1")
    assert [turn.question for turn in history] == ["q2", "q3"]
