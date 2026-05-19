from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state
from mini_rag.graph.prompts import COMPLETION_REFLECT_SYSTEM, GENERATE_ANSWER_SYSTEM, PLAN_INTENT_SYSTEM
from mini_rag.graph.time_contract import apply_weekday_date_if_possible
from mini_rag.graph.workflow import AgenticRAGWorkflow


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class RecordingLLM:
    def __init__(self, content: str = "{}"):
        self.content = content
        self.calls: list[list[tuple[str, str]]] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return FakeMessage(self.content)


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def test_default_workflow_keeps_explicit_rag_and_tool_branches(tmp_path: Path) -> None:
    workflow = AgenticRAGWorkflow(make_settings(tmp_path), llm=RecordingLLM())
    graph = workflow._compiled.get_graph()
    node_names = set(graph.nodes)

    assert "completion_reflect" in node_names
    assert "plan_retrieval" in node_names
    assert "retrieve" in node_names
    assert "call_tool" in node_names
    assert "execute_task_queue" not in node_names
    assert "reflect_evidence" not in node_names


def test_rag_trace_does_not_show_execute_task_queue(tmp_path: Path) -> None:
    from langchain_core.documents import Document

    class Retriever:
        def search(self, query, **_kwargs):
            return (
                [
                    Document(
                        page_content="报销制度要求发票真实有效。",
                        metadata={"source": "finance.md", "title_path": "报销制度", "chunk_id": "c1", "rank": 1},
                    )
                ],
                {"query": query, "result_count": 1, "results": [{"source": "finance.md", "chunk_id": "c1"}]},
            )

    llm = RecordingLLM(
        '{"message_type":"business_question","context_usage":"none","intent":"rag_fact","route":"rag",'
        '"standalone_query":"公司的报销制度","risk_level":"low","selected_tool":null,"selected_action":null,'
        '"tool_input":{},"time_requirement":{"has_time_requirement":false,"time_reference_type":"none","requires_current_datetime":false},'
        '"knowledge_requirement":{"requires_company_knowledge":true,"known_from_user_message":false,"should_use_rag":true},'
        '"execution_plan":{"tasks":[{"task_id":"t1","kind":"rag","objective":"查询公司报销制度","query":"公司的报销制度"}]},'
        '"missing_required_slots":[],"reason":"查制度"}'
    )
    llm.contents = [
        llm.content,
        '{"search_tasks":[{"query":"公司的报销制度","purpose":"answer","target_entity":null}],"reason":"查制度"}',
        '{"ready_to_answer":true,"completed_objectives":["查询公司报销制度"],"missing_objectives":[],"unsupported_parts":[],"next_action":"answer","followup_tasks":[],"reason":"已完成"}',
        "报销制度要求发票真实有效。",
    ]
    llm.invoke = lambda messages: (llm.calls.append(messages) or FakeMessage(llm.contents.pop(0)))

    workflow = AgenticRAGWorkflow(make_settings(tmp_path), llm=llm, retriever=Retriever())
    workflow._compiled = None
    state = workflow.run("公司的报销制度", role="admin")
    node_names = [item["node"] for item in state["node_trace"]]

    assert "plan_retrieval" in node_names
    assert "retrieve" in node_names
    assert "completion_reflect" in node_names
    assert "execute_task_queue" not in node_names


def test_prompt_contract_keeps_reflection_within_user_scope() -> None:
    assert "不得新增用户没有明确要求的细节目标" in COMPLETION_REFLECT_SYSTEM
    assert "宽泛询问制度" in COMPLETION_REFLECT_SYSTEM
    assert "不要把制度自动扩展成限额、评分细则、审计细则" in COMPLETION_REFLECT_SYSTEM
    assert "execution_plan.tasks 必须覆盖用户当前消息中的所有子目标" in PLAN_INTENT_SYSTEM


def test_answer_prompt_forbids_hallucinated_weekday_labels() -> None:
    assert "不要自行补充星期几" in GENERATE_ANSWER_SYSTEM
    assert "不要声明系统时间偏差" in GENERATE_ANSWER_SYSTEM
    assert "必须复述其中已有的 title、date、weekday_zh、time、location" in GENERATE_ANSWER_SYSTEM


def test_answer_prompt_preserves_canonical_business_status_messages() -> None:
    assert "没有匹配日程可删除" in GENERATE_ANSWER_SYSTEM
    assert "无权修改公司日程" in GENERATE_ANSWER_SYSTEM


def test_plan_prompt_defines_attendance_leave_and_absent_semantics() -> None:
    assert "请假" in PLAN_INTENT_SYSTEM
    assert "status_filter=leave" in PLAN_INTENT_SYSTEM
    assert "缺勤" in PLAN_INTENT_SYSTEM
    assert "status_filter=absent" in PLAN_INTENT_SYSTEM


def test_weekday_offsets_are_resolved_without_finalize_llm(tmp_path: Path) -> None:
    llm = RecordingLLM('{"action":"create","date":"2026-05-19"}')
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("帮我新增下周二上午八点的会议", role="admin")
    state["selected_action"] = "create"
    state["time_reference"] = {
        "has_time_requirement": True,
        "time_reference_type": "relative",
        "canonical_relative": None,
        "requires_current_datetime": True,
    }

    payload = {"action": "create", "title": "会议", "time": "08:00"}
    apply_weekday_date_if_possible(
        "manage_company_calendar",
        payload,
        {"current_date": "2026-05-15", "ranges": {"next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}}},
        time_reference={"time_reference_type": "relative", "canonical_relative": "next_week"},
        selected_action="create",
        reference_text=state["question"],
    )

    assert payload["date"] == "2026-05-19"
    assert llm.calls == []
    assert not hasattr(nodes, "_finalize_tool_input_with_llm")
