from langchain_core.documents import Document

from mini_rag.config import Settings
from mini_rag.graph.prompts import format_answer_user
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state
from mini_rag.graph.utils import compact_evidence_text


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class RecordingLLM:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)
        self.calls: list[list] = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.contents:
            return FakeMessage(self.contents.pop(0))
        return FakeMessage("{}")


class RecordingRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query, top_k=None, candidate_k=None, retrieval_mode=None, enable_rerank=None):
        self.queries.append(query)
        return (
            [
                Document(
                    page_content=f"{query} 的证据，包含完整回答所需信息。",
                    metadata={
                        "source": "manual.md",
                        "title_path": "手册 > 模块",
                        "chunk_id": f"chunk-{len(self.queries)}",
                        "rank": 1,
                    },
                )
            ],
            {
                "query": query,
                "retrieval_engine": "hybrid",
                "rerank_enabled": True,
                "rerank_cache_hit": False,
                "result_count": 1,
                "results": [{"source": "manual.md", "chunk_id": f"chunk-{len(self.queries)}"}],
            },
        )


class DuplicateRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query, top_k=None, candidate_k=None, retrieval_mode=None, enable_rerank=None):
        self.queries.append(query)
        return (
            [
                Document(
                    page_content="重复证据",
                    metadata={
                        "source": "manual.md",
                        "title_path": "手册 > 模块",
                        "chunk_id": "same-chunk",
                        "rank": 1,
                    },
                )
            ],
            {"query": query, "result_count": 1, "results": [{"source": "manual.md", "chunk_id": "same-chunk"}]},
        )


def make_settings(tmp_path, **overrides):
    values = {
        "DASHSCOPE_API_KEY": "test-key",
        "CONTEXT_DB_PATH": tmp_path / "context.sqlite3",
        "LANGGRAPH_CHECKPOINT_DB_PATH": tmp_path / "checkpoints.sqlite3",
        "AGENT_RUNTIME": "langgraph",
        "RERANK_ENABLED": True,
        "AGENT_MAX_FOLLOWUP_TASKS": 2,
        "AGENT_ENABLE_RETRIEVAL_CACHE": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_default_reflection_rounds_allow_one_followup_batch_without_env():
    settings = Settings(DASHSCOPE_API_KEY="test-key", _env_file=None)

    assert settings.agent_reflect_max_rounds == 2
    assert settings.agent_max_search_tasks == 3
    assert settings.agent_evidence_char_limit == 2200


def test_understand_query_combines_route_without_second_llm_call(tmp_path):
    llm = RecordingLLM(
        [
            """
            {
              "intent": "direct",
              "route": "direct",
              "standalone_query": "你是什么模型",
              "topic": "",
              "entities": [],
              "risk_level": "low",
              "required_tools": [],
              "reason": "模型身份问题无需检索"
            }
            """
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RecordingRetriever())
    state = create_initial_state("你是什么模型")

    state = nodes.understand_query(state)
    state = nodes.route(state)

    assert len(llm.calls) == 1
    assert state["route"] == "direct"
    assert state["standalone_query"] == "你是什么模型"


def test_retrieve_records_cache_hit_for_repeated_query_in_same_run(tmp_path):
    retriever = RecordingRetriever()
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]), retriever=retriever)
    state = create_initial_state("智能客服平台包含哪些核心模块")
    state["pending_search_tasks"] = [{"query": "智能客服平台 核心模块"}]

    state = nodes.retrieve(state)
    state["pending_search_tasks"] = [{"query": " 智能客服平台   核心模块 "}]
    state = nodes.retrieve(state)

    assert retriever.queries == ["智能客服平台 核心模块"]
    cache_events = [
        obs for obs in state["observations"]
        if obs.get("type") == "tool" and obs.get("retrieval_trace", {}).get("retrieval_cache_hit") is True
    ]
    assert cache_events
    assert cache_events[0]["retrieval_trace"]["rerank_cache_hit"] is True


def test_after_retrieve_skips_reflection_when_single_query_has_evidence(tmp_path):
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]), retriever=RecordingRetriever())
    state = create_initial_state("智能客服平台包含哪些核心模块")
    state["route"] = "rag"
    state["pending_search_tasks"] = [{"query": "智能客服平台 核心模块"}]

    state = nodes.retrieve(state)

    assert nodes.after_retrieve(state) == "generate_answer"
    assert state["skipped_reflection_reason"] == "single_query_has_evidence"


def test_multi_entity_plan_preserves_llm_strategy_and_caps_tasks(tmp_path):
    llm = RecordingLLM(
        [
            '{"search_tasks":[{"query":"在线会话","purpose":"a","target_entity":"在线会话"},'
            '{"query":"工单管理","purpose":"b","target_entity":"工单管理"},'
            '{"query":"知识库管理","purpose":"c","target_entity":"知识库管理"},'
            '{"query":"智能机器人","purpose":"d","target_entity":"智能机器人"}],"reason":"多实体"}'
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RecordingRetriever())
    state = create_initial_state("介绍一下这些模块")
    state["intent"] = "rag_explain"
    state["topic"] = "智能客服平台"
    state["entities"] = ["在线会话", "工单管理", "知识库管理"]
    state["standalone_query"] = "介绍智能客服平台的在线会话、工单管理、知识库管理"

    state = nodes.plan_retrieval(state)

    assert [task["query"] for task in state["search_tasks"]] == ["在线会话", "工单管理", "知识库管理"]
    assert [task["target_entity"] for task in state["search_tasks"]] == ["在线会话", "工单管理", "知识库管理"]


def test_reflection_followup_tasks_are_capped(tmp_path):
    llm = RecordingLLM(
        [
            """
            {
              "is_sufficient": false,
              "can_answer_partial": true,
              "missing_information": ["a", "b", "c", "d"],
              "followup_tasks": [
                {"query": "补充 A", "purpose": "补 A", "target_entity": "A"},
                {"query": "补充 B", "purpose": "补 B", "target_entity": "B"},
                {"query": "补充 C", "purpose": "补 C", "target_entity": "C"},
                {"query": "补充 D", "purpose": "补 D", "target_entity": "D"}
              ],
              "reason": "只补最重要缺口"
            }
            """
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path, AGENT_REFLECT_MAX_ROUNDS=3), llm=llm, retriever=RecordingRetriever())
    state = create_initial_state("介绍这些模块")
    state["retrieved_docs"] = [
        Document(page_content="已有证据", metadata={"source": "manual.md", "chunk_id": "c1"})
    ]

    state = nodes.reflect_evidence(state)

    assert [task["query"] for task in state["pending_search_tasks"]] == ["补充 A", "补充 B"]


def test_reflection_respects_llm_decision_to_stop_retrieval(tmp_path):
    llm = RecordingLLM(
        [
            """
            {
              "is_sufficient": false,
              "can_answer_partial": true,
              "should_continue_retrieval": false,
              "missing_information": ["数据报表", "系统配置"],
              "followup_tasks": [
                {"query": "智能客服平台 数据报表 功能说明", "purpose": "补数据报表", "target_entity": "数据报表"},
                {"query": "智能客服平台 系统配置 功能说明", "purpose": "补系统配置", "target_entity": "系统配置"}
              ],
              "stop_reason": "继续检索大概率重复命中概述",
              "reason": "已有部分证据，可以部分回答"
            }
            """
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path, AGENT_REFLECT_MAX_ROUNDS=5), llm=llm, retriever=RecordingRetriever())
    state = create_initial_state("介绍这些模块")
    state["reflect_round"] = 1
    state["retrieved_docs"] = [
        Document(page_content="已有模块说明", metadata={"source": "manual.md", "chunk_id": "c1"})
    ]

    state = nodes.reflect_evidence(state)

    assert state["pending_search_tasks"] == []
    assert state["evidence_assessment"]["stop_reason"] == "继续检索大概率重复命中概述"
    assert nodes.after_reflect(state) == "generate_answer"


def test_reflection_allows_llm_decision_to_continue_retrieval(tmp_path):
    llm = RecordingLLM(
        [
            """
            {
              "is_sufficient": false,
              "can_answer_partial": true,
              "should_continue_retrieval": true,
              "missing_information": ["数据报表", "系统配置"],
              "followup_tasks": [
                {"query": "智能客服平台 数据报表 功能说明", "purpose": "补数据报表", "target_entity": "数据报表"},
                {"query": "智能客服平台 系统配置 功能说明", "purpose": "补系统配置", "target_entity": "系统配置"}
              ],
              "stop_reason": "",
              "reason": "这两个补检索仍可能提供直接证据"
            }
            """
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path, AGENT_REFLECT_MAX_ROUNDS=5), llm=llm, retriever=RecordingRetriever())
    state = create_initial_state("介绍这些模块")
    state["reflect_round"] = 1
    state["retrieved_docs"] = [
        Document(page_content="已有模块说明", metadata={"source": "manual.md", "chunk_id": "c1"})
    ]

    state = nodes.reflect_evidence(state)

    assert [task["query"] for task in state["pending_search_tasks"]] == [
        "智能客服平台 数据报表 功能说明",
        "智能客服平台 系统配置 功能说明",
    ]
    assert nodes.after_reflect(state) == "retrieve"


def test_followup_retrieval_without_new_evidence_goes_to_answer(tmp_path):
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=RecordingLLM([]), retriever=DuplicateRetriever())
    state = create_initial_state("介绍这些模块")
    state["route"] = "rag"
    state["intent"] = "rag_explain"
    state["entities"] = ["在线会话", "工单管理"]
    state["retrieved_docs"] = [
        Document(page_content="重复证据", metadata={"source": "manual.md", "chunk_id": "same-chunk"})
    ]
    state["reflect_round"] = 1
    state["pending_search_tasks"] = [{"query": "智能客服平台 工单管理 功能说明"}]

    state = nodes.retrieve(state)

    assert state["retrieval_made_progress"] is False
    assert nodes.after_retrieve(state) == "generate_answer"
    assert state["skipped_reflection_reason"] == "followup_retrieval_no_new_evidence"


def test_rag_memory_update_uses_lightweight_path_for_short_history(tmp_path):
    llm = RecordingLLM([])
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RecordingRetriever())
    state = create_initial_state("智能客服平台包含哪些核心模块", session_id="s1")
    state["route"] = "rag"
    state["standalone_query"] = "智能客服平台包含哪些核心模块"
    state["final_answer"] = "智能客服平台包含在线会话和知识库。\n\n引用来源：manual.md"
    state["topic"] = "智能客服平台"
    state["entities"] = ["在线会话", "知识库"]

    state = nodes.update_memory(state)

    assert len(llm.calls) == 0
    assert state["memory_update"]["topic"] == "智能客服平台"
    assert "引用来源" not in state["memory_update"]["memory_answer"]


def test_trace_contains_total_latency_and_llm_call_details(tmp_path):
    llm = RecordingLLM(
        [
            '{"intent":"direct","route":"direct","standalone_query":"你是什么模型","topic":"","entities":[],"risk_level":"low","required_tools":[],"reason":"direct"}',
            "我是测试模型",
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RecordingRetriever())
    state = create_initial_state("你是什么模型")

    state = nodes.understand_query(state)
    state = nodes.route(state)
    state = nodes.generate_answer(state)
    trace = nodes.build_trace(state)

    assert trace["total_latency_ms"] >= 0
    assert len(trace["llm_calls"]) == 2
    assert trace["llm_calls"][0]["node"] == "plan_intent"
    assert trace["llm_calls"][0]["prompt_chars"] > 0


def test_compact_evidence_defaults_keep_llm_context_small():
    docs = [
        Document(
            page_content=f"模块{i}说明：" + "很长的功能描述" * 80,
            metadata={"source": "manual.md", "title_path": f"手册 > 模块{i}", "chunk_id": f"c{i}"},
        )
        for i in range(10)
    ]

    brief = compact_evidence_text(docs)

    assert len(brief) <= 2200
    assert "很长的功能描述" in brief


def test_answer_prompt_omits_verbose_reflection_reason_and_followups():
    prompt = format_answer_user(
        question="介绍一下这些模块",
        standalone_query="介绍智能客服模块",
        route="rag",
        model_name="qwen3-max",
        evidence_assessment={
            "is_sufficient": False,
            "can_answer_partial": True,
            "should_continue_retrieval": False,
            "missing_information": ["数据报表"],
            "followup_tasks": [{"query": "很长的补充检索 query"}],
            "reason": "这是一段很长的反思理由" * 80,
            "stop_reason": "继续检索收益低",
        },
        evidence_text="[证据 1]\ntext: 数据报表未提供详细说明",
    )

    assert "这是一段很长的反思理由" not in prompt
    assert "很长的补充检索 query" not in prompt
    assert "数据报表" in prompt
    assert "继续检索收益低" in prompt
