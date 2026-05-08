from __future__ import annotations

from mini_rag.observability.trace_store import build_readable_trace, extract_latest_retrieval_trace


def test_extract_latest_retrieval_trace_from_observations() -> None:
    trace = {
        "observations": [
            {"type": "tool", "retrieval_trace": {"query": "old"}},
            {"type": "tool", "retrieval_trace": {"query": "new", "result_count": 3}},
        ]
    }
    assert extract_latest_retrieval_trace(trace) == {"query": "new", "result_count": 3}


def test_build_readable_trace_contains_steps() -> None:
    trace = {
        "trace_id": "trace_demo",
        "question": "智能客服平台有哪些核心模块？",
        "route": "rag",
        "node_trace": [
            {"node": "route", "latency_ms": 12},
            {"node": "generate_answer", "latency_ms": 20},
        ],
        "answer": "答案预览",
    }
    readable = build_readable_trace(trace)
    assert readable["trace_id"] == "trace_demo"
    assert [step["node"] for step in readable["steps"]] == ["route", "generate_answer"]
