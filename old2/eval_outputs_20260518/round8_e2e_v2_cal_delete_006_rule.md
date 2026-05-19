# Agent Evaluation Suite Report

- Generated at: `2026-05-17T12:42:41.247653+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 1 | 0 | 1 | 0.0000 | 21733.46 | 21733.46 |
| e2e | 1 | 0 | 1 | 0.0000 | 21733.46 | 21733.46 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 1 |
| executed_cases | 1 |
| infra_error_cases | 0 |
| agent_passed_cases | 0 |
| agent_failed_cases | 1 |
| agent_pass_rate | 0.0 |
| case_count | 1 |
| passed | 0 |
| failed | 1 |
| pass_rate | 0.0 |
| avg_latency_ms | 21733.46 |
| p95_latency_ms | 21733.46 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 1.0 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 0.0 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 0.0 |
| write_result_success | 0.0 |

## Failed Cases

### e2e / e2e_v2_cal_delete_006

- Question: 删除下周所有公司团建。
- Failure reasons: task_success, expected_tool_coverage, write_result_success, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "all_events", "event_type": "activity", "department": "all", "query": "删除下周所有公司团建。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询下周所有公司团建事件以获取 event_id", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "all_events", "event_type": "activity", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-24 的公司日程：\n- 2026-05-19 星期二 16:00-18:00 公司团建（城市公园，event_id：EVT-20260519-0001）\n- 2026-05-21 星期四 18:00-20:00 公司团建（团建餐厅，event_id：EVT-20260521-0002）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260519-0001", "date": "2026-05-19", "title": "公司团建", "type": "activity", "department": "all", "time": "16:00-18:00", "location": "城市公园", "description": "下周第一个团建活动，用于 update/delete 评测", "weekday_zh": "星期二"}, {"event_id": "EVT-20260521-0002", "date": "2026-05-21", "title": "公司团建", "type": "activity", "department": "all", "time": "18:00-20:00", "location": "团建餐厅", "description": "第二个团建活动", "weekday_zh": "星期四"}]}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "删除上一步查到的所有团建事件", "status": "needs_clarification", "tool_name": "manage_company_calendar", "action": "delete", "tool_input": {"action": "delete", "selector": {"event_type": "activity", "date_range": "next_week"}}, "result_summary": "匹配到多个日程，请指定要删除的 event_id 后再删除。", "tool_result": {"status": "needs_clarification", "action": "delete", "message": "匹配到多个日程，请指定要删除的 event_id 后再删除。"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，下周（2026-05-18 至 2026-05-24）共有两场公司团建活动：

- **2026-05-19 星期二 16:00-18:00**：公司团建（城市公园，event_id：EVT-20260519-0001）  
- **2026-05-21 星期四 18:00-20:00**：公司团建（团建餐厅，event_id：EVT-20260521-0002）

在尝试删除这些团建日程时，系统提示：“匹配到多个日程，请指定要删除的 event_id 后再删除。”

因此，若您希望删除全部两场团建，请明确指定两个 event_id（EVT-20260519-0001 和 EVT-20260521-0002）；或告知需要删除其中哪一场，以便执行后续操作。
