from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.orchestration.agentic_nodes import AgenticRAGNodes
from mini_rag.orchestration.state_factory import create_initial_state


class Message:
    def __init__(self, content: str):
        self.content = content


class QueueLLM:
    def __init__(self, contents: list[str]):
        self.contents = list(contents)

    def invoke(self, _messages):
        if self.contents:
            return Message(self.contents.pop(0))
        return Message('{"next_action":"finish","finish_reason":"done"}')


class FakeDoc:
    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


class RetryRetriever:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, **_kwargs):
        self.queries.append(query)
        if len(self.queries) == 1:
            return [
                FakeDoc(
                    "这是第一次检索的候选内容，应该只在 debug trace 中完整保留。",
                    {"source": "product.md", "title_path": "产品案例", "chunk_id": "p1", "rank": 1},
                )
            ], {"retrieval_cache_hit": False}
        return [
            FakeDoc(
                "报销制度要求提交发票、支付凭证和审批单。",
                {"source": "finance.md", "title_path": "报销制度", "chunk_id": "f1", "rank": 1},
            )
        ], {"retrieval_cache_hit": False}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def test_mainline_log_records_all_current_mainline_stages_without_debug_payloads(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"smalltalk","requires_tools":false,"requires_rag":false,"tasks":[],"answer_style":"concise"}',
            "你好，我在。",
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RetryRetriever())
    state = create_initial_state("你好", role="employee", user_id="u1", override_now="2026-05-18T09:30:00+08:00")

    for step in (
        nodes.build_runtime_context,
        nodes.plan_with_llm,
        nodes.resolve_plan_time,
        nodes.validate_plan,
        nodes.react_execute,
        nodes.answer_with_llm,
        nodes.update_memory,
    ):
        state = step(state)

    log = state["mainline_log"]
    assert [item["stage"] for item in log] == [
        "runtime_context",
        "plan_with_llm",
        "resolve_plan_time",
        "validate_plan",
        "react_execute",
        "answer_with_llm",
        "update_memory",
    ]
    assert log[0]["title"] == "构建运行上下文"
    assert all(any("\u4e00" <= char <= "\u9fff" for char in item["title"]) for item in log)

    rendered = state["mainline_log_text"]
    assert "构建运行上下文" in rendered
    assert "生成执行计划" in rendered
    assert "本轮没有需要解析的相对时间" in rendered
    assert "output_schema" not in rendered
    assert "candidate_sources" not in rendered
    assert "raw_result" not in rendered
    assert len(rendered) < 5000


def test_rag_retry_mainline_log_summarizes_judge_reflect_and_supporting_count(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"rag","requires_tools":false,"requires_rag":true,'
            '"tasks":[{"task_id":"rag","kind":"rag","objective":"介绍公司的报销制度","rag_query":"公司报销制度"}],'
            '"answer_style":"concise"}',
            '{"answerable":false,"sufficiency":"low","supporting_source_ids":[],"missing_evidence":["报销依据"],"reason":"第一次证据不足"}',
            '{"should_retry":true,"reason":"同主题补检索",'
            '"retrieval_query":"报销 费用报销 发票 支付凭证 审批流程 报销单 FIN-EXP-2026",'
            '"target_kbs":["finance"],"query_scope":"same_topic","expected_evidence":["报销材料"]}',
            '{"answerable":true,"sufficiency":"high","supporting_source_ids":["f1"],"missing_evidence":[],"reason":"第二次证据充分"}',
            "公司报销制度要求提交发票、支付凭证和审批单。",
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RetryRetriever())
    state = create_initial_state("介绍一下公司的报销制度", role="admin", kb_ids=["finance"])

    for step in (
        nodes.build_runtime_context,
        nodes.plan_with_llm,
        nodes.resolve_plan_time,
        nodes.validate_plan,
        nodes.react_execute,
        nodes.answer_with_llm,
        nodes.update_memory,
    ):
        state = step(state)

    text = state["mainline_log_text"]
    assert "检索次数：2" in text
    assert "Evidence Judge：充分" in text
    assert "RAG Reflect：已触发" in text
    assert "supporting_sources：1" in text
    assert "第一次检索的候选内容" not in text
    assert "报销制度要求提交发票、支付凭证和审批单" not in text
