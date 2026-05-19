from __future__ import annotations

from mini_rag.graph.prompts import GENERATE_ANSWER_SYSTEM, PLAN_INTENT_SYSTEM, format_answer_user


def test_answer_prompt_keeps_multi_task_question_and_groups_evidence() -> None:
    prompt = format_answer_user(
        question="介绍一下公司的报销制度和员工培养制度",
        standalone_query="公司的报销制度",
        route="rag",
        model_name="qwen-plus",
        evidence_assessment={},
        evidence_text="[证据 1] 全局重复证据不应在任务证据已存在时再次出现",
        task_results=[
            {
                "kind": "rag",
                "objective": "查询公司的报销制度",
                "status": "ok",
                "sources": [
                    {
                        "source": "finance.md",
                        "title_path": "报销制度 > 基本要求",
                        "chunk_id": "fin-1",
                        "preview": "报销需提供真实有效发票。",
                    }
                ],
            },
            {
                "kind": "rag",
                "objective": "查询公司的员工培养制度",
                "status": "ok",
                "sources": [
                    {
                        "source": "hr.md",
                        "title_path": "员工培训与成长路径 > 学习计划",
                        "chunk_id": "hr-1",
                        "preview": "新员工应在 30 天内完成基础培训。",
                    }
                ],
            },
        ],
    )

    assert "用户原始问题：介绍一下公司的报销制度和员工培养制度" in prompt
    assert "独立问题：公司的报销制度" not in prompt
    assert "必须逐项覆盖每个任务" in prompt
    assert "查询公司的报销制度" in prompt
    assert "查询公司的员工培养制度" in prompt
    assert "报销需提供真实有效发票" in prompt
    assert "新员工应在 30 天内完成基础培训" in prompt
    assert "全局重复证据" not in prompt
    assert "status" not in prompt
    assert "candidate_sources" not in prompt


def test_planner_prompt_prefers_compact_task_output() -> None:
    assert "优先输出精简 JSON" in PLAN_INTENT_SYSTEM
    assert "RAG task 通常只需要 task_id/kind/objective/query" in PLAN_INTENT_SYSTEM
    assert "不要输出无意义的 null、空数组、空对象或 false 默认字段" in PLAN_INTENT_SYSTEM


def test_answer_prompt_is_route_aware_for_tool_results() -> None:
    prompt = format_answer_user(
        question="这周公司有什么日程安排",
        standalone_query="这周公司有什么日程安排",
        route="tool",
        model_name="qwen-plus",
        evidence_assessment={},
        evidence_text="",
        task_results=[
            {
                "kind": "tool",
                "objective": "查询本周公司日程安排",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "result_summary": "2026-05-11 至 2026-05-17 有 1 条公司日程。",
            }
        ],
    )

    assert "route：tool" in prompt
    assert "工具答案只能基于工具结果回答" in prompt
    assert "不要输出 source/title_path/chunk_id" in prompt
    assert "RAG 答案末尾列出引用来源" not in prompt


def test_answer_prompt_passes_tool_status_and_canonical_message() -> None:
    prompt = format_answer_user(
        question="删除 2099-01-01 的所有公司会议",
        standalone_query="删除 2099-01-01 的所有公司会议",
        route="tool",
        model_name="qwen-plus",
        evidence_assessment={},
        evidence_text="",
        task_results=[
            {
                "kind": "tool",
                "objective": "删除匹配会议",
                "status": "skipped",
                "tool_name": "manage_company_calendar",
                "action": "delete",
                "tool_result": {
                    "action": "delete",
                    "status": "skipped",
                    "message": "没有匹配日程可删除，无需删除。",
                },
                "result_summary": "没有匹配日程可删除，无需删除。",
            }
        ],
    )

    assert "任务状态" in prompt
    assert "工具状态" in prompt
    assert "工具消息" in prompt
    assert "没有匹配日程可删除，无需删除" in prompt


def test_answer_prompt_passes_calendar_events_with_weekday_contract() -> None:
    prompt = format_answer_user(
        question="下周公司有什么日程安排",
        standalone_query="下周公司有什么日程安排",
        route="tool",
        model_name="qwen-plus",
        evidence_assessment={},
        evidence_text="",
        task_results=[
            {
                "kind": "tool",
                "objective": "查询下周公司日程安排",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_result": {
                    "action": "query",
                    "events": [
                        {
                            "event_id": "EVT-20260518-0001",
                            "date": "2026-05-18",
                            "weekday_zh": "星期一",
                            "time": "10:00-11:00",
                            "title": "周例会",
                            "type": "meeting",
                            "department": "all",
                            "location": "线上",
                        }
                    ],
                },
            }
        ],
    )

    assert "calendar_events" in prompt
    assert "EVT-20260518-0001" in prompt
    assert "星期一" in prompt
    assert "只能使用工具结果中的 weekday_zh" in GENERATE_ANSWER_SYSTEM
    assert "不要列出工具结果中不存在的日期安排" in GENERATE_ANSWER_SYSTEM


def test_answer_prompt_passes_datetime_ranges_without_self_computed_weekdays() -> None:
    prompt = format_answer_user(
        question="上周一到上周日分别是哪几天？",
        standalone_query="上周一到上周日分别是哪几天？",
        route="tool",
        model_name="qwen-plus",
        evidence_assessment={},
        evidence_text="",
        task_results=[
            {
                "kind": "tool",
                "objective": "获取当前日期时间和相对日期范围",
                "status": "ok",
                "tool_name": "get_current_datetime",
                "action": "*",
                "tool_result": {
                    "current_date": "2026-05-17",
                    "current_time": "02:35:27",
                    "weekday": "Sunday",
                    "weekday_zh": "星期日",
                    "timezone": "Asia/Shanghai",
                    "ranges": {
                        "last_week": {
                            "start_date": "2026-05-04",
                            "end_date": "2026-05-10",
                        },
                        "this_month": {"start_date": "2026-05-01", "end_date": "2026-05-31"},
                    },
                },
            }
        ],
    )

    assert "datetime_facts" in prompt
    assert "last_week" in prompt
    assert "2026-05-04" in prompt
    assert "2026-05-10" in prompt
    assert "星期一" not in prompt
    assert '"days"' not in prompt
    assert "this_month" not in prompt
    assert "2026-05-31" not in prompt


def test_answer_prompt_passes_calendar_write_event_details() -> None:
    prompt = format_answer_user(
        question="把 event_id 为 EVT-20260522-0002 的日程改成客户复盘会，时间 16:00-17:00，地点会议室 C。",
        standalone_query="更新指定日程",
        route="tool",
        model_name="qwen-plus",
        evidence_assessment={},
        evidence_text="",
        task_results=[
            {
                "kind": "tool",
                "objective": "更新指定 event_id 的日程信息",
                "status": "ok",
                "tool_name": "manage_company_calendar",
                "action": "update",
                "tool_result": {
                    "status": "updated",
                    "message": "公司日程已更新",
                    "event": {
                        "event_id": "EVT-20260522-0002",
                        "date": "2026-05-22",
                        "weekday_zh": "星期五",
                        "time": "16:00-17:00",
                        "title": "客户复盘会",
                        "location": "会议室 C",
                        "type": "meeting",
                        "department": "销售部",
                    },
                },
            }
        ],
    )

    assert "calendar_event" in prompt
    assert "客户复盘会" in prompt
    assert "16:00-17:00" in prompt
    assert "会议室 C" in prompt


def test_answer_prompt_passes_attendance_structured_details() -> None:
    prompt = format_answer_user(
        question="查询 2026-05-12 研发部缺勤记录",
        standalone_query="查询 2026-05-12 研发部缺勤记录",
        route="tool",
        model_name="qwen-plus",
        evidence_assessment={},
        evidence_text="",
        task_results=[
            {
                "kind": "tool",
                "objective": "查询 2026-05-12 研发部缺勤记录",
                "tool_name": "query_attendance_summary",
                "action": "query",
                "tool_result": {
                    "start_date": "2026-05-12",
                    "end_date": "2026-05-12",
                    "summary": {"total_records": 2, "absent": 1},
                    "status_filter": "absent",
                    "filtered_count": 1,
                    "by_employee": [
                        {
                            "employee_id": "u002",
                            "name": "李四",
                            "department": "研发部",
                            "total_records": 1,
                            "absent": 1,
                        }
                    ],
                    "records": [
                        {
                            "date": "2026-05-12",
                            "employee_id": "u002",
                            "name": "李四",
                            "department": "研发部",
                            "status": "absent",
                        }
                    ],
                },
            }
        ],
    )

    assert "attendance_summary" in prompt
    assert "attendance_by_employee" in prompt
    assert "attendance_records" in prompt
    assert "李四" in prompt
    assert "研发部" in prompt


def test_planner_prompt_knows_datetime_tool_examples() -> None:
    assert "selected_tool=get_current_datetime" in PLAN_INTENT_SYSTEM
    assert "current_message=现在的日期和时间" in PLAN_INTENT_SYSTEM
    assert "current_message=这周公司有什么日程安排" in PLAN_INTENT_SYSTEM
    assert "不要在 tool_input 中填写你猜测的 start_date/end_date/date" in PLAN_INTENT_SYSTEM
