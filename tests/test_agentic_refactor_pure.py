from pathlib import Path

from mini_rag.agent.context_store import SQLiteContextStore
from mini_rag.graph.utils import strip_citations_and_metadata, safe_json_loads, dedupe_keep_order


def test_strip_citations_and_metadata_removes_technical_fields():
    raw = """
智能客服平台包含以下核心模块：在线会话、工单管理。

引用来源：
- source: 06_产品使用手册_智能客服平台.md
- title_path: 智能客服平台产品使用手册 > 1. 产品概述
- chunk_id: abc:chunk:0001
"""
    cleaned = strip_citations_and_metadata(raw)
    assert "在线会话" in cleaned
    assert "工单管理" in cleaned
    assert "source" not in cleaned.lower()
    assert "title_path" not in cleaned.lower()
    assert "chunk_id" not in cleaned.lower()


def test_context_store_separates_memory_answer(tmp_path: Path):
    store = SQLiteContextStore(tmp_path / "context.sqlite3")
    answer = "答案正文\n\n引用来源：\n- source: a.md\n- title_path: A > B\n- chunk_id: 123"
    memory_answer = strip_citations_and_metadata(answer)
    store.append_turn(
        session_id="s1",
        question="有哪些模块",
        standalone_query="智能客服平台有哪些模块",
        answer=answer,
        sources=[{"source": "a.md"}],
        trace={"debug": True},
        memory_answer=memory_answer,
        intent="rag_fact",
        topic="智能客服平台",
        entities=["在线会话", "工单管理"],
    )
    ctx = store.get_context("s1", max_turns=5)
    assert len(ctx.turns) == 1
    turn = ctx.turns[0]
    assert "引用来源" in turn.answer
    assert "source" not in turn.memory_answer.lower()
    assert turn.intent == "rag_fact"
    assert turn.entities == ["在线会话", "工单管理"]


def test_safe_json_loads_handles_fenced_json():
    payload = safe_json_loads('```json\n{"route":"rag"}\n```', default={})
    assert payload["route"] == "rag"


def test_dedupe_keep_order():
    assert dedupe_keep_order(["a", "b", "a", "c"]) == ["a", "b", "c"]

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state


class _Msg:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    def invoke(self, messages):
        system = messages[0][1]
        user = messages[1][1]
        if "结构化 Planner" in system or "问题改写" in system:
            return _Msg(
                '{"message_type":"business_question","context_usage":"none","intent":"direct","route":"direct",'
                '"standalone_query":"你是什么模型","topic":"","entities":[],"risk_level":"low",'
                '"selected_tool":null,"selected_action":null,"required_tools":[],"tool_input":{},'
                '"needs_time_resolution":false,"relative_time":null,"missing_required_slots":[],"reason":"模型身份问题"}'
            )
        if "路由节点" in system:
            return _Msg('{"route":"direct","risk_level":"low","required_tools":[],"reason":"无需检索"}')
        if "严谨的企业知识库 Agent" in system:
            return _Msg("我是当前项目配置的聊天模型：qwen-plus。")
        if "会话记忆整理节点" in system:
            return _Msg('{"memory_answer":"我是当前项目配置的聊天模型：qwen-plus。","summary":"用户询问模型身份。","topic":"","entities":[]}')
        return _Msg("{}")


def test_direct_path_with_fake_llm(tmp_path: Path):
    settings = Settings(context_db_path=tmp_path / "ctx.sqlite3")
    nodes = AgenticRAGNodes(settings, llm=FakeLLM(), retriever=None)
    state = create_initial_state("你是什么模型", session_id="s1")
    state = nodes.load_context(state)
    state = nodes.understand_query(state)
    state = nodes.route(state)
    assert nodes.should_retrieve(state) == "generate_answer"
    state = nodes.generate_answer(state)
    state = nodes.update_memory(state)
    assert state["route"] == "direct"
    assert "qwen-plus" in state["final_answer"]
    ctx = nodes.context_store.get_context("s1", max_turns=5)
    assert ctx.turns[0].memory_answer

from mini_rag.graph.utils import compact_evidence_text


class DummyDoc:
    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


def test_multi_entity_explain_plan_keeps_llm_tasks_and_caps_count(tmp_path: Path):
    settings = Settings(context_db_path=tmp_path / "ctx.sqlite3", agent_entity_top_k=2, agent_entity_candidate_k=6)
    nodes = AgenticRAGNodes(settings, llm=FakeLLM(), retriever=None)
    state = create_initial_state("介绍一下这些模块", session_id="s1")
    state["intent"] = "rag_explain"
    state["topic"] = "智能客服平台"
    state["entities"] = ["在线会话", "工单管理"]
    tasks = nodes._optimize_search_tasks(
        state,
        [
            {"query": "智能客服平台 在线会话 功能说明", "purpose": "a", "target_entity": "在线会话"},
            {"query": "智能客服平台 工单管理 功能说明", "purpose": "b", "target_entity": "工单管理"},
            {"query": "智能客服平台 知识库管理 功能说明", "purpose": "c", "target_entity": "知识库管理"},
            {"query": "智能客服平台 智能机器人 功能说明", "purpose": "d", "target_entity": "智能机器人"},
        ],
    )
    assert [task["target_entity"] for task in tasks] == ["在线会话", "工单管理", "知识库管理"]
    assert all(task["top_k"] == settings.top_k for task in tasks)
    assert all(task["candidate_k"] == settings.candidate_k for task in tasks)


def test_compact_evidence_prioritizes_entity_and_limits_text():
    docs = [
        DummyDoc(page_content="无关内容" * 200, metadata={"chunk_id": "0", "source": "a.md", "title_path": "概述"}),
        DummyDoc(page_content="在线会话模块支持访客接入和转人工。" * 20, metadata={"chunk_id": "1", "source": "b.md", "title_path": "在线会话"}),
        DummyDoc(page_content="工单管理模块支持创建、分派和关闭。" * 20, metadata={"chunk_id": "2", "source": "c.md", "title_path": "工单管理"}),
    ]
    brief = compact_evidence_text(docs, entities=["工单管理"], limit_each=80, max_total_chars=600)
    assert "工单管理" in brief
    assert "chunk_id: 2" in brief
    assert len(brief) <= 600
