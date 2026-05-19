from mini_rag.agent.graph_agent import build_readable_steps


def test_build_readable_steps_explains_langgraph_flow():
    trace = {
        "question": "简单介绍一下前三个模块",
        "session_id": "user001",
        "route": "rag",
        "router_reason": "需要查知识库",
        "risk_level": "low",
        "standalone_query": "智能客服平台前三个模块",
        "context_events": [
            {"node": "build_runtime_context", "history_turn_count": 1, "has_summary": True},
            {"node": "manage_context", "context_reason": "选择上一轮", "selected_history_count": 1},
        ],
        "node_trace": [
            {"node": "build_runtime_context", "latency_ms": 1.0, "error": None},
            {"node": "manage_context", "latency_ms": 2.0, "error": None},
            {"node": "llm_router", "latency_ms": 3.0, "error": None},
            {"node": "react_execute", "latency_ms": 4.0, "error": None},
            {"node": "reflect", "latency_ms": 0.1, "error": None},
            {"node": "answer_with_llm", "latency_ms": 5.0, "error": None},
            {"node": "persist_context", "latency_ms": 0.5, "error": None},
        ],
        "tool_calls": [{"tool_name": "search_knowledge_base", "args": {"query": "智能客服平台前三个模块"}}],
        "observations": [
            {
                "type": "tool",
                "tool_name": "search_knowledge_base",
                "retrieval_trace": {
                    "retrieval_engine": "hybrid",
                    "result_count": 2,
                    "results": [
                        {"source": "manual.md", "title_path": "手册 > A", "chunk_id": "c1", "preview": "内容"}
                    ],
                },
            }
        ],
        "sources": [{"source": "manual.md", "title_path": "手册 > A", "chunk_id": "c1", "preview": "内容"}],
        "answer": "最终答案",
    }

    steps = build_readable_steps(trace)

    assert [step["node"] for step in steps] == [
        "build_runtime_context",
        "manage_context",
        "llm_router",
        "react_execute",
        "reflect",
        "answer_with_llm",
        "persist_context",
    ]
    assert steps[0]["input"]["session_id"] == "user001"
    assert steps[2]["output"]["route"] == "rag"
    assert steps[3]["output"]["tool_name"] == "search_knowledge_base"
    assert steps[3]["output"]["retrieved_sources"][0]["source"] == "manual.md"
