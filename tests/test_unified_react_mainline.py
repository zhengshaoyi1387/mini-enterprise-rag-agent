from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.orchestration.agentic_nodes import AgenticRAGNodes
from mini_rag.orchestration.state_factory import create_initial_state
from mini_rag.orchestration.react_executor import ReActExecutor, ReActGuardrailViolation


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


class FinanceRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query: str, **_kwargs):
        self.queries.append(query)
        return [
            FakeDoc(
                "费用报销需提交真实发票、审批单和差旅行程单；采购报销按预算与审批规则执行。",
                {
                    "kb_id": "finance",
                    "source": "finance/finance_01_reimbursement_travel_procurement_2026.md",
                    "title_path": "报销、差旅与采购制度 2026 > 关键规则与阈值",
                    "chunk_id": "finance-reimbursement-1",
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


def test_new_workflow_uses_single_runtime_plan_time_react_answer_chain(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"datetime","requires_tools":false,"requires_rag":false,'
            '"tasks":[{"task_id":"t1","kind":"answer","objective":"回答后天是星期几","time_expression":"后天"}],'
            '"answer_style":"concise"}',
            '{"next_action":"finish","finish_reason":"time fact is already resolved"}',
            "后天是 2026-05-20，星期三。",
        ]
    )
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("后天是星期几？", role="employee", override_now="2026-05-18T09:30:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)
    state = nodes.react_execute(state)
    state = nodes.answer_with_llm(state)

    assert [entry["node"] for entry in state["node_trace"]] == [
        "build_runtime_context",
        "plan_with_llm",
        "resolve_plan_time",
        "validate_plan",
        "react_execute",
        "answer_with_llm",
    ]
    assert state["resolved_time_facts"][0]["items"][0]["start_date"] == "2026-05-20"
    assert state["resolved_time_facts"][0]["items"][0]["weekday_zh"] == "星期三"
    assert state["final_answer"] == "后天是 2026-05-20，星期三。"
    assert len(llm.calls) == 3


def test_smalltalk_empty_plan_does_not_fallback_to_rag(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"smalltalk","requires_tools":false,"requires_rag":false,"tasks":[],"answer_style":"concise"}',
            "你好，我在。",
        ]
    )
    retriever = FinanceRetriever()
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=retriever)
    state = create_initial_state("你好", role="employee", override_now="2026-05-18T09:30:00+08:00")

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)
    assert state["intent"] == "smalltalk"
    assert state["plan_validation"]["validation_status"] == "valid"
    state = nodes.react_execute(state)
    state = nodes.answer_with_llm(state)

    assert state["route"] == "direct"
    assert state["execution_plan"]["tasks"] == []
    assert retriever.queries == []
    assert all(call.get("tool_name") != "search_knowledge_base" for call in state["tool_calls"])
    assert state["final_answer"] == "你好，我在。"
    assert len(llm.calls) == 2


def test_mixed_flow_accepts_finance_reimbursement_supporting_source(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"overall_intent":"mixed","requires_tools":true,"requires_rag":true,'
            '"tasks":['
            '{"task_id":"cal","kind":"tool","objective":"查看这周会议","tool_name":"manage_company_calendar","action":"query","time_expression":"本周","tool_input":{"action":"query","event_type":"meeting","department":"all"}},'
            '{"task_id":"rag","kind":"rag","objective":"介绍公司的报销制度","rag_query":"公司报销制度"},'
            '{"task_id":"att","kind":"tool","objective":"查询上周出勤情况","tool_name":"query_attendance_summary","action":"query","time_expression":"上周","tool_input":{"department":"all","include_records":false}}'
            '],"answer_style":"concise"}',
            '{"answerable":true,"sufficiency":"high","supporting_source_ids":["finance-reimbursement-1"],"missing_evidence":[],"reason":"证据覆盖报销制度概要"}',
            "会议：已查询；报销制度：需真实发票和审批单；出勤情况：已查询。",
        ]
    )
    retriever = FinanceRetriever()
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm, retriever=retriever)
    state = create_initial_state(
        "再查看一下这周的会议，然后介绍一下公司的报销制度，再查一下上周的出勤情况",
        role="admin",
        override_now="2026-05-18T09:30:00+08:00",
    )

    state = nodes.build_runtime_context(state)
    state = nodes.plan_with_llm(state)
    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)
    state = nodes.react_execute(state)
    state = nodes.answer_with_llm(state)

    assert [result["kind"] for result in state["task_results"]] == ["tool", "rag", "tool"]
    rag_result = next(result for result in state["task_results"] if result["kind"] == "rag")
    assert rag_result["status"] == "ok"
    assert rag_result["sources"][0]["source"] == "finance/finance_01_reimbursement_travel_procurement_2026.md"
    assert {"manage_company_calendar", "search_knowledge_base", "query_attendance_summary"} <= {
        call.get("tool_name") for call in state["tool_calls"]
    }
    assert "会议" in state["final_answer"]
    assert "报销制度" in state["final_answer"]
    assert "出勤情况" in state["final_answer"]


def test_react_executor_blocks_duplicate_tool_input() -> None:
    executor = ReActExecutor(max_steps=4)
    state = {
        "question": "查明天会议",
        "execution_plan": {
            "tasks": [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "start_date": "2026-05-19", "end_date": "2026-05-19"},
                },
                {
                    "task_id": "t2",
                    "kind": "tool",
                    "tool": "manage_company_calendar",
                    "action": "query",
                    "tool_input": {"action": "query", "start_date": "2026-05-19", "end_date": "2026-05-19"},
                },
            ]
        },
        "completed_tasks": [],
        "observations": [],
    }
    actions = [
        {
            "next_action": "call_tool",
            "task_id": "t2",
            "tool_name": "manage_company_calendar",
            "tool_input": {"action": "query", "start_date": "2026-05-19", "end_date": "2026-05-19"},
        },
        {
            "next_action": "call_tool",
            "task_id": "t1",
            "tool_name": "manage_company_calendar",
            "tool_input": {"action": "query", "start_date": "2026-05-19", "end_date": "2026-05-19"},
        },
    ]

    try:
        executor.run(
            state,
            next_action=lambda _state, _step, _remaining: actions.pop(0),
            call_tool=lambda _task, _action: {"status": "success", "summary": "ok", "raw_result": {}},
            search_rag=lambda _task, _action: {"status": "success", "summary": "ok", "raw_result": {}},
        )
    except ReActGuardrailViolation as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate tool call should be blocked")


def test_resolve_plan_time_splits_multi_calendar_query(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=QueueLLM([]))
    state = create_initial_state("查今天和明天分别有什么会议", role="employee", override_now="2026-05-18T09:30:00+08:00")
    state = nodes.build_runtime_context(state)
    state["raw_plan"] = {
        "overall_intent": "calendar",
        "requires_tools": True,
        "tasks": [
            {
                "task_id": "t1",
                "kind": "tool",
                "objective": "查询今天和明天的会议",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "time_expression": "今天和明天",
                "tool_input": {"action": "query", "event_type": "meeting", "department": "all"},
            }
        ],
    }
    state["execution_plan"] = {"tasks": [dict(state["raw_plan"]["tasks"][0])]}

    state = nodes.resolve_plan_time(state)

    tasks = state["execution_plan"]["tasks"]
    assert [task["time_expression"] for task in tasks] == ["今天", "明天"]
    assert [(task["tool_input"]["start_date"], task["tool_input"]["end_date"]) for task in tasks] == [
        ("2026-05-18", "2026-05-18"),
        ("2026-05-19", "2026-05-19"),
    ]


def test_resolve_plan_time_removes_symbolic_date_after_start_end_are_resolved(tmp_path: Path) -> None:
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=QueueLLM([]))
    state = create_initial_state("查下周团建", role="admin", override_now="2026-05-18T09:30:00+08:00")
    state = nodes.build_runtime_context(state)
    state["execution_plan"] = {
        "tasks": [
            {
                "task_id": "t1",
                "kind": "tool",
                "objective": "查询下周团建",
                "tool": "manage_company_calendar",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "time_expression": "下周",
                "tool_input": {"action": "query", "event_type": "activity", "date": "下周"},
            }
        ]
    }

    state = nodes.resolve_plan_time(state)
    state = nodes.validate_plan(state)

    task_input = state["execution_plan"]["tasks"][0]["tool_input"]
    assert task_input["start_date"] == "2026-05-25"
    assert task_input["end_date"] == "2026-05-31"
    assert "date" not in task_input
    assert state["plan_validation"]["validation_status"] == "valid"
