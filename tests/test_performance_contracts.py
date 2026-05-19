from __future__ import annotations

from pathlib import Path

from mini_rag.capabilities.rag.evidence_judge import RAG_EVIDENCE_JUDGE_SYSTEM, build_evidence_judge_prompt
from mini_rag.capabilities.rag.service import RAGRetrievalService
from mini_rag.config import Settings
from mini_rag.graph.prompts import PLAN_WITH_LLM_SYSTEM, format_plan_with_llm_user
from mini_rag.models.qwen import build_qwen_planner_model, model_name_for
from mini_rag.planning.context_policy import build_context_packet
from mini_rag.tools.daily_tools import build_default_tool_registry


class Message:
    def __init__(self, content: str):
        self.content = content


class QueueLLM:
    def __init__(self, outputs: list[str]):
        self.outputs = list(outputs)
        self.calls: list[list[tuple[str, str]]] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return Message(self.outputs.pop(0))


class FakeDoc:
    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


class TimedRetriever:
    def __init__(self):
        self.queries: list[str] = []

    def search(self, query: str, **_kwargs):
        self.queries.append(query)
        return [
            FakeDoc(
                "报销需要发票、支付凭证和审批单。",
                {
                    "kb_id": "finance",
                    "source": "finance.md",
                    "title_path": "报销制度",
                    "chunk_id": "finance-1",
                    "rank": 1,
                },
            )
        ], {"retrieval_latency_ms": 12.5}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        RERANK_ENABLED=False,
    )


def test_rag_task_result_records_fine_grained_latency_trace(tmp_path: Path) -> None:
    llm = QueueLLM(
        [
            '{"answerable":true,"sufficiency":"high","supporting_source_ids":["finance-1"],"missing_evidence":[],"reason":"证据充分"}'
        ]
    )
    retriever = TimedRetriever()
    service = RAGRetrievalService(
        make_settings(tmp_path),
        get_retriever=lambda: retriever,
        get_role_policies=lambda _state: None,
        llm=llm,
    )
    state = {
        "role": "admin",
        "question": "报销怎么申请？",
        "used_kbs": ["finance"],
        "pending_search_tasks": [{"task_id": "rag", "query": "公司报销制度", "objective": "报销怎么申请？"}],
        "observations": [],
        "tool_calls": [],
        "task_results": [],
        "completed_tasks": [],
    }

    service.retrieve(state)
    latency = state["task_results"][0]["latency_trace"]

    assert latency["retrieve_1_ms"] >= 0
    assert latency["evidence_judge_1_ms"] >= 0
    assert latency["rag_reflect_ms"] == 0
    assert latency["retrieve_2_ms"] == 0
    assert latency["evidence_judge_2_ms"] == 0
    assert latency["selected_sources_count"] == 1
    assert latency["candidate_sources_count"] == 1
    assert latency["supporting_sources_count"] == 1
    assert latency["triggered_reflect"] is False


def test_independent_model_config_names_are_resolved(tmp_path: Path) -> None:
    settings = Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        QWEN_CHAT_MODEL="answer-base",
        QWEN_CONTROL_MODEL="control-base",
        PLANNER_MODEL="planner-fast",
        RAG_JUDGE_MODEL="judge-fast",
        RAG_REFLECT_MODEL="reflect-fast",
        ANSWER_MODEL="answer-rich",
    )

    assert model_name_for(settings, "planner") == "planner-fast"
    assert model_name_for(settings, "rag_judge") == "judge-fast"
    assert model_name_for(settings, "rag_reflect") == "reflect-fast"
    assert model_name_for(settings, "answer") == "answer-rich"
    assert model_name_for(settings, "control") == "control-base"


def test_planner_and_judge_prompts_are_compact_enough_for_latency() -> None:
    user_prompt = build_evidence_judge_prompt(
        original_question="报销怎么申请？",
        rag_task_objective="说明报销申请方式",
        candidate_sources=[
            {
                "chunk_id": "finance-1",
                "kb_id": "finance",
                "source": "finance.md",
                "title_path": "报销制度",
                "preview": "报销需要发票、支付凭证和审批单。" * 80,
            }
        ],
        attempt=1,
    )

    assert len(PLAN_WITH_LLM_SYSTEM) < 760
    assert len(RAG_EVIDENCE_JUDGE_SYSTEM) < 750
    assert len(user_prompt) < 1600


def test_independent_planner_question_drops_previous_tool_context() -> None:
    previous_tool_context = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {"action": "query", "start_date": "2026-05-20", "end_date": "2026-05-20"},
        "result_summary": "2026-05-20 至 2026-05-20 的公司会议安排：项目复盘会",
        "events": [
            {
                "event_id": "EVT-20260520-0002",
                "date": "2026-05-20",
                "weekday_zh": "星期三",
                "time": "10:00-11:00",
                "title": "项目复盘会",
                "location": "会议室B",
            }
        ],
    }

    context = build_context_packet(
        history=[],
        previous_tool_context=previous_tool_context,
        question="查询一下后天的公司会议",
    )

    assert "previous_tool_context" not in context


def test_followup_selector_planner_question_keeps_previous_tool_context() -> None:
    previous_tool_context = {
        "domain": "calendar",
        "tool_name": "manage_company_calendar",
        "tool_input": {"action": "query", "start_date": "2026-05-20", "end_date": "2026-05-20"},
        "events": [{"event_id": "EVT-1", "date": "2026-05-20", "time": "10:00-11:00", "title": "项目复盘会"}],
    }

    context = build_context_packet(
        history=[],
        previous_tool_context=previous_tool_context,
        question="把第一个会议改到 10 点",
    )

    assert context["previous_tool_context"]["events"][0]["event_id"] == "EVT-1"


def test_plan_prompt_uses_compact_runtime_and_does_not_request_resolved_dates() -> None:
    prompt = format_plan_with_llm_user(
        question="查询一下后天的公司会议",
        role="admin",
        planning_context={},
        capability_catalog='cal=manage_company_calendar(query/create/update/delete);att=query_attendance_summary;rag=search_knowledge_base;dt=get_current_datetime',
        permissions={"role": "admin", "allowed_kbs": ["finance", "hr", "it", "product", "public"], "tool_actions": {"manage_company_calendar": ["create", "delete", "query", "update"]}},
        time_context={"current_date": "2026-05-19", "current_time": "22:26:54", "weekday_zh": "星期二", "timezone": "Asia/Shanghai", "ranges": {"huge": "not needed"}},
    )

    assert "tool_actions" not in prompt
    assert "ranges" not in prompt
    assert "start_date" not in PLAN_WITH_LLM_SYSTEM
    assert "end_date" not in PLAN_WITH_LLM_SYSTEM
    assert "单行压缩 JSON" in PLAN_WITH_LLM_SYSTEM
    assert len(prompt) < 700


def test_planner_keeps_calendar_event_type_guidance_for_correctness() -> None:
    summary = build_default_tool_registry().format_tool_routing_summary_for_prompt(role="admin")

    assert "event_type" in summary
    assert "会议=meeting" in summary
    assert "培训=training" in summary
    assert "团建=activity" in summary
    assert "公司会议" in PLAN_WITH_LLM_SYSTEM
    assert "event_type=meeting" in PLAN_WITH_LLM_SYSTEM


def test_planner_model_uses_output_token_cap(tmp_path: Path) -> None:
    settings = Settings(
        DASHSCOPE_API_KEY="test-key",
        CONTEXT_DB_PATH=tmp_path / "context.sqlite3",
        AUTH_DB_PATH=tmp_path / "auth.sqlite3",
        LANGGRAPH_CHECKPOINT_DB_PATH=tmp_path / "checkpoints.sqlite3",
        PLANNER_MAX_TOKENS=321,
    )

    model = build_qwen_planner_model(settings)

    assert getattr(model, "max_tokens", None) == 321
