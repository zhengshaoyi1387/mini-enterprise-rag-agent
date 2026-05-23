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
        self.calls: list[list[tuple[str, str]]] = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.contents:
            return Message(self.contents.pop(0))
        return Message("最终回答。")


class FakeDoc:
    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


class RelatedFinanceRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query: str, **_kwargs):
        self.queries.append(query)
        return [
            FakeDoc(
                "报销材料包括行程单、发票、支付凭证。审批流程为直属负责人审批后提交财务复核。",
                {
                    "kb_id": "finance",
                    "source": "finance/finance_01_reimbursement_travel_procurement_2026.md",
                    "title_path": "报销、差旅与采购制度 2026 > 相关参考",
                    "chunk_id": "finance-related-1",
                    "rank": 1,
                },
            )
        ], {"retrieval_cache_hit": False}


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def test_policy_gap_checker_triggers_for_unanswerable_policy_related_sources(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"rag","requires_tools":false,"requires_rag":true,'
            '"tasks":[{"task_id":"t1","kind":"rag","objective":"出差酒店花费是否可以报销",'
            '"rag_query":"出差酒店花费是否可以报销"}],"answer_style":"concise"}',
            '{"answerable":false,"sufficiency":"low","supporting_source_ids":[],'
            '"related_source_ids":["finance-related-1"],"missing_evidence":["缺少酒店费用是否可报销的明确条款"],'
            '"reason":"只有相关报销材料和流程证据"}',
            '{"should_retry":false,"reason":"相关证据不足且不补检索","retrieval_query":null,'
            '"target_kbs":["finance"],"query_scope":"same_topic","expected_evidence":[]}',
            "当前只找到相关参考，缺少酒店费用是否可报销的明确条款。",
        ]
    )
    nodes = AgenticRAGNodes(_settings(tmp_path), llm=llm, retriever=RelatedFinanceRetriever())
    state = create_initial_state(
        "出差酒店花费是否可以报销？",
        role="admin",
        kb_ids=["finance"],
        override_now="2026-05-18T09:30:00+08:00",
    )

    for step in (
        nodes.build_runtime_context,
        nodes.plan_with_llm,
        nodes.resolve_plan_time,
        nodes.validate_plan,
        nodes.react_execute,
        nodes.answer_with_llm,
    ):
        state = step(state)

    rag_result = next(item for item in state["task_results"] if item["kind"] == "rag")
    assert rag_result["status"] == "empty"
    assert rag_result["sources"] == []
    assert rag_result["related_sources"]
    gap = rag_result["policy_gap_check"]
    assert gap["ok"] is True
    assert gap["skill_name"] == "policy_gap_checker"
    assert gap["overall"] == "partial"
    missing_slots = {item["slot"] for item in gap["missing_slots"]}
    assert {"是否允许", "明确政策条款"} & missing_slots
    assert gap["trace"]["evidence_items_count"] == 1
    assert gap["trace"]["missing_slots_count"] >= 1
    assert state["sources"] == []
    assert state["answer_packet"]["status"] == "insufficient_evidence"
    assert "证据缺口分析" in str(state["answer_packet"])


def test_policy_gap_checker_does_not_trigger_when_evidence_is_answerable(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"rag","requires_tools":false,"requires_rag":true,'
            '"tasks":[{"task_id":"t1","kind":"rag","objective":"报销流程是什么",'
            '"rag_query":"报销流程是什么"}],"answer_style":"concise"}',
            '{"answerable":true,"sufficiency":"high","supporting_source_ids":["finance-related-1"],'
            '"related_source_ids":[],"missing_evidence":[],"reason":"流程证据充分"}',
            "报销流程需要负责人审批后财务复核。",
        ]
    )
    nodes = AgenticRAGNodes(_settings(tmp_path), llm=llm, retriever=RelatedFinanceRetriever())
    state = create_initial_state("报销流程是什么？", role="admin", kb_ids=["finance"])

    for step in (
        nodes.build_runtime_context,
        nodes.plan_with_llm,
        nodes.resolve_plan_time,
        nodes.validate_plan,
        nodes.react_execute,
    ):
        state = step(state)

    rag_result = next(item for item in state["task_results"] if item["kind"] == "rag")
    assert rag_result["status"] == "ok"
    assert "policy_gap_check" not in rag_result
    assert rag_result["sources"]


def test_policy_gap_checker_failure_does_not_change_rag_task_state(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"rag","requires_tools":false,"requires_rag":true,'
            '"tasks":[{"task_id":"t1","kind":"rag","objective":"出差酒店花费是否可以报销",'
            '"rag_query":"出差酒店花费是否可以报销"}],"answer_style":"concise"}',
            '{"answerable":false,"sufficiency":"low","supporting_source_ids":[],'
            '"related_source_ids":["finance-related-1"],"missing_evidence":["缺少明确条款"],"reason":"只有相关证据"}',
            '{"should_retry":false,"reason":"不补检索","retrieval_query":null,'
            '"target_kbs":["finance"],"query_scope":"same_topic","expected_evidence":[]}',
        ]
    )
    nodes = AgenticRAGNodes(_settings(tmp_path), llm=llm, retriever=RelatedFinanceRetriever())
    nodes.rag_service.skill_registry.scan_skills(tmp_path / "missing_skills")
    state = create_initial_state("出差酒店花费是否可以报销？", role="admin", kb_ids=["finance"])

    for step in (
        nodes.build_runtime_context,
        nodes.plan_with_llm,
        nodes.resolve_plan_time,
        nodes.validate_plan,
        nodes.react_execute,
    ):
        state = step(state)

    rag_result = next(item for item in state["task_results"] if item["kind"] == "rag")
    assert rag_result["status"] == "empty"
    assert rag_result["sources"] == []
    assert rag_result["related_sources"]
    assert rag_result["policy_gap_check"]["ok"] is False
    assert rag_result["policy_gap_check"]["error"]["type"] == "skill_unavailable"


def test_policy_gap_checker_uses_related_sources_from_first_attempt_when_retry_is_empty(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"rag","requires_tools":false,"requires_rag":true,'
            '"tasks":[{"task_id":"t1","kind":"rag","objective":"出差酒店花费是否可以报销",'
            '"rag_query":"出差酒店花费是否可以报销"}],"answer_style":"concise"}',
            '{"answerable":false,"sufficiency":"low","supporting_source_ids":[],'
            '"related_source_ids":["finance-related-1"],"missing_evidence":["缺少酒店费用是否可报销的明确条款"],'
            '"reason":"只有相关报销材料和流程证据"}',
            '{"should_retry":true,"reason":"补充检索酒店住宿费",'
            '"retrieval_query":"出差期间酒店住宿费用报销规定","target_kbs":["finance"],'
            '"query_scope":"same_topic","expected_evidence":["酒店住宿费用是否可报销"]}',
            '{"answerable":false,"sufficiency":"low","supporting_source_ids":[],'
            '"related_source_ids":[],"missing_evidence":["仍缺少明确条款"],'
            '"reason":"retry 没有直接证据"}',
        ]
    )
    nodes = AgenticRAGNodes(_settings(tmp_path), llm=llm, retriever=RelatedFinanceRetriever())
    state = create_initial_state(
        "出差酒店花费是否可以报销？",
        role="admin",
        kb_ids=["finance"],
        override_now="2026-05-18T09:30:00+08:00",
    )

    for step in (
        nodes.build_runtime_context,
        nodes.plan_with_llm,
        nodes.resolve_plan_time,
        nodes.validate_plan,
        nodes.react_execute,
    ):
        state = step(state)

    rag_result = next(item for item in state["task_results"] if item["kind"] == "rag")
    assert rag_result["status"] == "empty"
    assert rag_result["sources"] == []
    assert rag_result["related_sources"]
    assert rag_result["latency_trace"]["related_sources_count"] >= 1
    assert rag_result["policy_gap_check"]["ok"] is True
    assert rag_result["latency_trace"]["policy_gap_triggered"] is True
