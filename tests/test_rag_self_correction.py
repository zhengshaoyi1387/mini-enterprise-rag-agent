from __future__ import annotations

from pathlib import Path

from mini_rag.answer.packet import build_answer_packet
from mini_rag.capabilities.rag.self_correct import validate_retrieval_query
from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state


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
        return Message('{"next_action":"finish","finish_reason":"done"}')


class FakeDoc:
    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


class RetryFinanceRetriever:
    def __init__(self, *, second_query_supports: bool = True):
        self.queries: list[str] = []
        self.second_query_supports = second_query_supports

    def search(self, query: str, **_kwargs):
        self.queries.append(query)
        if "FIN-EXP-2026" in query and self.second_query_supports:
            return [
                FakeDoc(
                    "费用报销需提交真实发票、支付凭证和审批单；FIN-EXP-2026 要求报销单字段完整。",
                    {
                        "kb_id": "finance",
                        "source": "finance/finance_01_reimbursement_travel_procurement_2026.md",
                        "title_path": "报销、差旅与采购制度 2026 > FIN-EXP-2026",
                        "chunk_id": "finance-reimbursement-1",
                        "rank": 1,
                    },
                )
            ], {"retrieval_cache_hit": False}
        return [
            FakeDoc(
                "智能客服平台案例介绍，包含会话质检、产品 API 和 SLA 指标。",
                {
                    "kb_id": "product",
                    "source": "product/product_01_agent_platform_overview.md",
                    "title_path": "产品平台案例",
                    "chunk_id": "product-overview-1",
                    "rank": 1,
                },
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


def test_smalltalk_still_does_not_trigger_rag_self_correction(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"smalltalk","requires_tools":false,"requires_rag":false,"tasks":[],"answer_style":"concise"}',
            "你好，我在。",
        ]
    )
    retriever = RetryFinanceRetriever()
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=retriever)
    state = create_initial_state("你好", role="employee", override_now="2026-05-18T09:30:00+08:00")

    for step in (nodes.build_runtime_context, nodes.plan_with_llm, nodes.resolve_plan_time, nodes.validate_plan, nodes.react_execute, nodes.answer_with_llm):
        state = step(state)

    assert retriever.queries == []
    assert all(call.get("tool_name") != "search_knowledge_base" for call in state["tool_calls"])
    assert state["route"] == "direct"


def test_reimbursement_rag_task_uses_llm_judge_then_retries_once(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"rag","requires_tools":false,"requires_rag":true,'
            '"tasks":[{"task_id":"rag","kind":"rag","objective":"介绍公司的报销制度","rag_query":"公司报销制度"}],'
            '"answer_style":"concise"}',
            '{"next_action":"search_rag","task_id":"rag","rag_query":"公司报销制度"}',
            '{"answerable":false,"sufficiency":"low","supporting_source_ids":[],"missing_evidence":["报销制度依据"],"reason":"候选证据不覆盖原问题"}',
            '{"should_retry":true,"reason":"在同一问题范围内补齐报销制度依据",'
            '"retrieval_query":"报销 费用报销 发票 支付凭证 审批流程 报销单 FIN-EXP-2026",'
            '"target_kbs":["finance"],"query_scope":"same_topic","expected_evidence":["报销材料","审批流程"]}',
            '{"answerable":true,"sufficiency":"high","supporting_source_ids":["finance-reimbursement-1"],"missing_evidence":[],"reason":"证据覆盖原问题"}',
            "公司报销制度要求提供真实发票、支付凭证和审批单。",
        ]
    )
    retriever = RetryFinanceRetriever()
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=retriever)
    state = create_initial_state("介绍一下公司的报销制度", role="admin", kb_ids=["finance", "product"])

    for step in (nodes.build_runtime_context, nodes.plan_with_llm, nodes.resolve_plan_time, nodes.validate_plan, nodes.react_execute, nodes.answer_with_llm):
        state = step(state)

    assert retriever.queries == [
        "公司报销制度",
        "报销 费用报销 发票 支付凭证 审批流程 报销单 FIN-EXP-2026",
    ]
    rag_results = [item for item in state["task_results"] if item["kind"] == "rag"]
    assert rag_results[0]["status"] == "ok"
    assert rag_results[0]["executed_queries"] == retriever.queries
    assert rag_results[0]["sources"][0]["source"] == "finance/finance_01_reimbursement_travel_procurement_2026.md"
    assert rag_results[0]["evidence_judgments"][-1]["supporting_source_ids"] == ["finance-reimbursement-1"]
    assert sum(1 for call in state["tool_calls"] if call.get("tool_name") == "search_knowledge_base") == 2
    assert any(item.get("type") == "rag_reflection" for item in state["observations"])
    assert any(call.get("node") == "rag_evidence_judge" for call in state["llm_calls"])
    assert any(call.get("node") == "rag_reflect" for call in state["llm_calls"])


def test_retrieval_query_validation_uses_guardrails_not_keyword_lists() -> None:
    assert validate_retrieval_query(
        original_query="公司报销制度",
        retrieval_query="报销制度 绩效 招聘 系统权限 部署",
        target_kbs=["finance"],
        allowed_kbs=["finance", "hr", "it"],
        candidate_sources=[],
        query_scope="same_topic",
    )
    assert not validate_retrieval_query(
        original_query="公司报销制度",
        retrieval_query="报销 费用报销 发票",
        target_kbs=["finance", "secret"],
        allowed_kbs=["finance"],
        candidate_sources=[],
        query_scope="same_topic",
    )
    assert not validate_retrieval_query(
        original_query="公司报销制度",
        retrieval_query="报销 费用报销 发票",
        target_kbs=["finance"],
        allowed_kbs=["finance"],
        candidate_sources=[],
        query_scope="expanded",
    )


def test_candidate_evidence_stays_out_of_answer_packet_when_retry_fails() -> None:
    packet = build_answer_packet(
        {
            "route": "rag",
            "task_results": [
                {
                    "task_id": "rag",
                    "kind": "rag",
                    "status": "empty",
                    "objective": "介绍公司的报销制度",
                    "query": "公司报销制度",
                    "executed_queries": ["公司报销制度", "报销 费用报销 发票"],
                    "sources": [],
                    "candidate_sources": [{"preview": "候选正文不应给 Answer LLM。"}],
                }
            ],
            "sources": [],
            "candidate_sources": [{"preview": "候选正文不应给 Answer LLM。"}],
        }
    )

    packet_text = str(packet)
    assert "当前可访问知识库未找到明确支持证据" in packet_text
    assert "候选正文不应给 Answer LLM" not in packet_text


def test_final_answer_theme_remains_original_question_not_retry_query(tmp_path: Path) -> None:
    llm = QueueLLM(["这是最终回答。"])
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RetryFinanceRetriever())
    state = create_initial_state("介绍一下公司的报销制度", role="admin")
    state["route"] = "rag"
    state["task_results"] = [
        {
            "task_id": "rag",
            "kind": "rag",
            "status": "ok",
            "objective": "介绍公司的报销制度",
            "query": "公司报销制度",
            "executed_queries": ["公司报销制度", "报销 费用报销 发票 支付凭证 审批流程 报销单 FIN-EXP-2026"],
            "sources": [{"source": "finance.md", "title_path": "报销制度", "preview": "发票和审批单。"}],
            "evidence_judgments": [{"answerable": True, "sufficiency": "high", "supporting_source_ids": ["finance.md#idx:1"]}],
        }
    ]
    state["sources"] = [{"source": "finance.md", "title_path": "报销制度", "preview": "发票和审批单。"}]

    state = nodes.answer_with_llm(state)
    prompt = llm.calls[-1][1][1]

    assert "用户原始问题：介绍一下公司的报销制度" in prompt
    assert "用户原始问题：报销 费用报销" not in prompt
    assert state["answer_packet"]["answer_question"] == "介绍一下公司的报销制度"


def test_mixed_rag_retry_success_makes_answer_packet_success(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"mixed","requires_tools":true,"requires_rag":true,'
            '"tasks":['
            '{"task_id":"cal","kind":"tool","objective":"查看这周会议","tool_name":"manage_company_calendar","action":"query","time_expression":"本周","tool_input":{"action":"query","event_type":"meeting","department":"all"}},'
            '{"task_id":"rag","kind":"rag","objective":"介绍公司的报销制度","rag_query":"公司报销制度"},'
            '{"task_id":"att","kind":"tool","objective":"查询上周出勤情况","tool_name":"query_attendance_summary","action":"query","time_expression":"上周","tool_input":{"department":"all","include_records":false}}'
            '],"answer_style":"concise"}',
            '{"next_action":"call_tool","task_id":"cal","tool_name":"manage_company_calendar"}',
            '{"next_action":"search_rag","task_id":"rag","rag_query":"公司报销制度"}',
            '{"answerable":false,"sufficiency":"low","supporting_source_ids":[],"missing_evidence":["报销制度依据"],"reason":"候选证据不足"}',
            '{"should_retry":true,"reason":"需要同主题补检索",'
            '"retrieval_query":"报销 费用报销 发票 支付凭证 审批流程 报销单 FIN-EXP-2026",'
            '"target_kbs":["finance"],"query_scope":"same_topic","expected_evidence":["报销材料"]}',
            '{"answerable":true,"sufficiency":"high","supporting_source_ids":["finance-reimbursement-1"],"missing_evidence":[],"reason":"证据充分"}',
            '{"next_action":"call_tool","task_id":"att","tool_name":"query_attendance_summary"}',
            "会议、报销制度和出勤情况均已汇总。",
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=RetryFinanceRetriever())
    state = create_initial_state(
        "再查看一下这周的会议，然后介绍一下公司的报销制度，再查一下上周的出勤情况",
        role="admin",
        kb_ids=["finance", "product"],
        override_now="2026-05-18T09:30:00+08:00",
    )

    for step in (nodes.build_runtime_context, nodes.plan_with_llm, nodes.resolve_plan_time, nodes.validate_plan, nodes.react_execute, nodes.answer_with_llm):
        state = step(state)

    assert [result["kind"] for result in state["task_results"]] == ["tool", "rag", "tool"]
    assert next(result for result in state["task_results"] if result["kind"] == "rag")["status"] == "ok"
    assert state["answer_packet"]["status"] == "success"
