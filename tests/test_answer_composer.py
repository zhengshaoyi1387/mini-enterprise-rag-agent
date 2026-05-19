from __future__ import annotations

from pathlib import Path

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class RecordingLLM:
    def __init__(self, content: str = "LLM 最终回答"):
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


def _last_user_prompt(llm: RecordingLLM) -> str:
    return llm.calls[-1][1][1]


def test_calendar_tool_answer_goes_through_llm_with_compact_facts_and_omits_event_id(tmp_path: Path) -> None:
    llm = RecordingLLM("根据工具查询结果，下周有周例会，时间 10:00-11:00，地点会议室A。")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("下周公司有什么日程安排？", role="employee")
    state["route"] = "tool"
    state["task_results"] = [
        {
            "task_id": "calendar",
            "kind": "tool",
            "status": "ok",
            "tool_name": "manage_company_calendar",
            "action": "query",
            "tool_result": {
                "action": "query",
                "start_date": "2026-05-18",
                "end_date": "2026-05-24",
                "events": [
                    {
                        "event_id": "EVT-20260518-0001",
                        "date": "2026-05-18",
                        "weekday_zh": "星期一",
                        "time": "10:00-11:00",
                        "title": "周例会",
                        "location": "会议室A",
                        "type": "meeting",
                    }
                ],
            },
        }
    ]

    state = nodes.generate_answer(state)

    assert len(nodes.answer_llm.calls) == 1
    prompt = _last_user_prompt(nodes.answer_llm)
    assert "周例会" in prompt
    assert "星期一" in prompt
    assert "会议室A" in prompt
    assert "EVT-20260518-0001" not in prompt
    assert "周例会" in state["final_answer"]
    assert "会议室A" in state["final_answer"]
    assert "EVT-20260518-0001" not in state["final_answer"]


def test_attendance_tool_answer_goes_through_llm_with_records(tmp_path: Path) -> None:
    llm = RecordingLLM("根据工具查询结果，2026-05-12 研发部有 1 条缺勤记录：李四。")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("查询 2026-05-12 研发部缺勤记录", role="hr")
    state["route"] = "tool"
    state["task_results"] = [
        {
            "task_id": "attendance",
            "kind": "tool",
            "status": "ok",
            "tool_name": "query_attendance_summary",
            "action": "query",
            "tool_result": {
                "start_date": "2026-05-12",
                "end_date": "2026-05-12",
                "status_filter": "absent",
                "filtered_count": 1,
                "records": [{"name": "李四", "department": "研发部", "status": "absent"}],
            },
        }
    ]

    state = nodes.generate_answer(state)

    assert len(nodes.answer_llm.calls) == 1
    prompt = _last_user_prompt(nodes.answer_llm)
    assert "李四" in prompt
    assert "研发部" in prompt
    assert "1 条缺勤记录" in state["final_answer"]
    assert "李四" in state["final_answer"]
    assert "研发部" in state["final_answer"]


def test_datetime_tool_answer_uses_returned_weekday_zh_only(tmp_path: Path) -> None:
    llm = RecordingLLM("今天是 2026-05-17，星期日。")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("今天星期几？", role="employee")
    state["route"] = "tool"
    state["task_results"] = [
        {
            "task_id": "datetime",
            "kind": "tool",
            "status": "ok",
            "tool_name": "get_current_datetime",
            "action": "*",
            "tool_result": {
                "current_date": "2026-05-17",
                "current_time": "09:00:00",
                "weekday": "Sunday",
                "weekday_zh": "星期日",
                "timezone": "Asia/Shanghai",
            },
        }
    ]

    state = nodes.generate_answer(state)

    assert len(nodes.answer_llm.calls) == 1
    assert "星期日" in _last_user_prompt(nodes.answer_llm)
    assert "星期日" in state["final_answer"]
    assert "Sunday" not in state["final_answer"]


def test_datetime_relative_question_uses_requested_range_not_current_date(tmp_path: Path) -> None:
    llm = RecordingLLM("明天是 2026-05-18。")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("明天是几号？", role="employee")
    state["route"] = "tool"
    state["task_results"] = [
        {
            "task_id": "datetime",
            "kind": "tool",
            "status": "ok",
            "objective": "明天是几号？",
            "tool_name": "get_current_datetime",
            "action": "*",
            "tool_result": {
                "current_date": "2026-05-17",
                "current_time": "09:00:00",
                "weekday_zh": "星期日",
                "timezone": "Asia/Shanghai",
                "ranges": {
                    "today": {"start_date": "2026-05-17", "end_date": "2026-05-17"},
                    "tomorrow": {"start_date": "2026-05-18", "end_date": "2026-05-18"},
                    "yesterday": {"start_date": "2026-05-16", "end_date": "2026-05-16"},
                    "this_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
                    "last_week": {"start_date": "2026-05-04", "end_date": "2026-05-10"},
                    "next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"},
                },
            },
        }
    ]

    state = nodes.generate_answer(state)

    assert len(nodes.answer_llm.calls) == 1
    assert "2026-05-18" in _last_user_prompt(nodes.answer_llm)
    assert "2026-05-18" in state["final_answer"]
    assert "当前日期：2026-05-17" not in state["final_answer"]


def test_datetime_week_range_answer_uses_compact_ranges(tmp_path: Path) -> None:
    llm = RecordingLLM("下周是 2026-05-18 至 2026-05-24。")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("下周是哪几天？", role="employee")
    state["route"] = "tool"
    state["task_results"] = [
        {
            "task_id": "datetime",
            "kind": "tool",
            "status": "ok",
            "objective": "下周是哪几天？",
            "tool_name": "get_current_datetime",
            "action": "*",
            "tool_result": {
                "current_date": "2026-05-17",
                "current_time": "09:00:00",
                "timezone": "Asia/Shanghai",
                "ranges": {"next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}},
            },
        }
    ]

    state = nodes.generate_answer(state)

    assert len(nodes.answer_llm.calls) == 1
    assert "2026-05-18" in _last_user_prompt(nodes.answer_llm)
    assert "2026-05-24" in _last_user_prompt(nodes.answer_llm)
    assert "2026-05-18 至 2026-05-24" in state["final_answer"]
    assert "days" not in state["final_answer"]


def test_rag_without_supporting_evidence_refuses_with_locked_fact_after_llm(tmp_path: Path) -> None:
    llm = RecordingLLM("不应该强答")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("出差报销回来要注意什么？", role="employee")
    state["route"] = "rag"
    state["task_results"] = [
        {
            "task_id": "policy",
            "kind": "rag",
            "status": "empty",
            "objective": "说明出差报销注意事项",
            "query": "出差报销回来要注意什么",
            "sources": [],
            "candidate_sources": [
                {
                    "source": "data/kbs/hr/hr_faq.md",
                    "title_path": "HR > 薪酬 FAQ",
                    "preview": "工资发放、薪酬保密、绩效奖金和社保公积金相关问答。",
                }
            ],
        }
    ]

    state = nodes.generate_answer(state)

    assert len(nodes.answer_llm.calls) == 1
    assert "当前可访问知识库未找到明确依据" in state["final_answer"]


def test_answer_prompt_excludes_candidate_evidence_when_supporting_sources_empty(tmp_path: Path) -> None:
    llm = RecordingLLM("当前可访问知识库未找到明确依据。")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("介绍公司的报销制度", role="employee")
    state["route"] = "rag"
    state["task_results"] = [
        {
            "task_id": "policy",
            "kind": "rag",
            "status": "empty",
            "objective": "介绍公司的报销制度",
            "query": "公司报销制度",
            "sources": [],
            "candidate_sources": [
                {
                    "source": "hr/hr_faq.md",
                    "title_path": "HR FAQ",
                    "preview": "候选正文：薪酬 FAQ，不应进入最终回答 prompt。",
                }
            ],
        }
    ]
    state["sources"] = []
    state["candidate_sources"] = [
        {"source": "hr/hr_faq.md", "preview": "候选正文：薪酬 FAQ，不应进入最终回答 prompt。"}
    ]
    state["evidence_brief"] = "候选正文：薪酬 FAQ，不应进入最终回答 prompt。"
    state["supporting_evidence_brief"] = ""

    state = nodes.generate_answer(state)

    prompt = _last_user_prompt(llm)
    assert "当前可访问知识库未找到明确支持证据" in prompt
    assert "候选正文：薪酬 FAQ" not in prompt


def test_mixed_tool_answer_is_preserved_when_rag_evidence_is_insufficient(tmp_path: Path) -> None:
    llm = RecordingLLM("不应该强答")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("我明天有会议吗？如果有，出差报销回来要注意什么？", role="employee")
    state["route"] = "rag"
    state["task_results"] = [
        {
            "task_id": "calendar",
            "kind": "tool",
            "status": "ok",
            "tool_name": "manage_company_calendar",
            "action": "query",
            "tool_result": {
                "events": [
                    {
                        "date": "2026-05-18",
                        "weekday_zh": "星期一",
                        "time": "10:00-11:00",
                        "title": "产品部 OKR 同步会",
                        "location": "会议室 B",
                        "type": "meeting",
                    }
                ]
            },
        },
        {
            "task_id": "policy",
            "kind": "rag",
            "status": "empty",
            "objective": "说明出差报销注意事项",
            "query": "出差报销回来要注意什么",
            "sources": [],
        },
    ]

    state = nodes.generate_answer(state)

    assert len(nodes.answer_llm.calls) == 1
    assert "产品部 OKR 同步会" in state["final_answer"]
    assert "当前可访问知识库未找到明确依据" in state["final_answer"]


def test_event_id_all_safety_explanation_goes_through_llm_but_is_locked(tmp_path: Path) -> None:
    llm = RecordingLLM("不应该调用")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("删除下周所有团建之前，先告诉我为什么不能直接 event_id=all。", role="admin")
    state["route"] = "rag"
    state["intent"] = "rag_fact"

    state = nodes.generate_answer(state)

    assert len(nodes.answer_llm.calls) == 1
    assert "event_id=all" in state["final_answer"]
    assert "不会执行删除" in state["final_answer"]


def test_safety_explanation_does_not_gain_permission_denial_without_permission_event(tmp_path: Path) -> None:
    llm = RecordingLLM("不能直接使用 event_id=all，因为它不是具体日程 ID；在目标明确前不会执行删除。")
    nodes = AgenticRAGNodes(make_settings(tmp_path), llm=llm)
    state = create_initial_state("删除下周所有团建之前，先告诉我为什么不能直接 event_id=all。", role="admin")
    state["route"] = "tool"
    state["task_results"] = [
        {
            "task_id": "calendar",
            "kind": "tool",
            "status": "ok",
            "tool_name": "manage_company_calendar",
            "action": "query",
            "tool_result": {"events": [{"title": "公司团建", "date": "2026-05-19"}]},
        }
    ]

    state = nodes.generate_answer(state)

    assert "不能直接使用 event_id=all" in state["final_answer"]
    assert "不会执行删除" in state["final_answer"]
    assert "无权执行" not in state["final_answer"]
