# Agent Evaluation Suite Report

- Generated at: `2026-05-17T16:32:45.669861+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 9 | 3 | 0.7500 | 11967.74 | 13660.07 |
| e2e | 12 | 9 | 3 | 0.7500 | 11967.74 | 13660.07 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 12 |
| executed_cases | 12 |
| infra_error_cases | 0 |
| agent_passed_cases | 9 |
| agent_failed_cases | 3 |
| agent_pass_rate | 0.75 |
| case_count | 12 |
| passed | 9 |
| failed | 3 |
| pass_rate | 0.75 |
| avg_latency_ms | 11967.74 |
| p95_latency_ms | 13660.07 |
| actual_success_no_blocked_tasks | 0.9167 |
| answer_must_contain_hit | 0.75 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 0.9167 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 0.9167 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 0.75 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_tool_001

- Question: 先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。
- Failure reasons: task_success, expected_tool_coverage, answer_must_contain_hit, multi_task_completion_rate, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-25", "end_date": "2026-05-31", "query_scope": "type_filtered", "event_type": "activity", "department": "all", "query": "先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询下周所有公司团建日程", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-25", "end_date": "2026-05-31", "query_scope": "type_filtered", "event_type": "activity", "department": "all"}, "result_summary": "2026-05-25 至 2026-05-31 没有匹配的公司日程。", "tool_result": {"action": "query", "events": []}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "将查询结果中的第一条团建日程更新为公司高层会议（21:00-22:00，会议室A）", "status": "skipped", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "selector": {"ordinal": 1}, "title": "公司高层会议", "type": "meeting", "time": "21:00-22:00", "location": "会议室A"}, "result_summary": "没有匹配日程可更新。", "tool_result": {"message": "没有匹配日程可更新。", "action": "update", "status": "skipped"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 2026-05-25 至 2026-05-31 没有匹配的公司日程。
没有匹配日程可更新。

### e2e / e2e_tool_006

- Question: 查询明天公司会议安排，然后告诉我能不能删除它。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-19", "end_date": "2026-05-19", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "查询明天公司会议安排，然后告诉我能不能删除它。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天公司会议安排", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-19", "end_date": "2026-05-19", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-19 至 2026-05-19 没有匹配的公司日程。", "tool_result": {"action": "query", "events": []}, "source_count": 0, "error_message": ""}]`
- Answer preview: 2026-05-19 至 2026-05-19 没有匹配的公司日程。
你没有权限修改公司日程，也无权执行删除、更新或新增操作；只有 admin 可以修改公司日程。

### e2e / e2e_tool_008

- Question: 现在的日期时间是多少？顺便查一下明天的公司会议安排。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai", "query": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-19", "end_date": "2026-05-19", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "获取当前日期和时间", "status": "ok", "tool_name": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}, "result_summary": "当前日期：2026-05-18，时间：00:32:04，星期：星期一，时区：Asia/Shanghai。", "tool_result": {"weekday": "Monday", "timezone": "Asia/Shanghai", "current_date": "2026-05-18", "current_time": "00:32:04", "ranges": {"today": {"start_date": "2026-05-18", "end_date": "2026-05-18"}, "yesterday": {"start_date": "2026-05-17", "end_date": "2026-05-17"}, "tomorrow": {"start_date": "2026-05-19", "end_date": "2026-05-19"}, "day_after_tomorrow": {"start_date": "2026-05-20", "end_date": "2026-05-20"}, "this_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}, "last_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"}, "next_week": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "week_after_next": {"start_date": "2026-06-01", "end_date": "2026-06-07"}, "next_next_week": {"start_date": "2026-06-01", "end_date": "2026-06-07"}, "this_month": {"start_date": "2026-05-01", "end_date": "2026-05-31"}, "last_month": {"start_date": "2026-04-01", "end_date": "2026-04-30"}, "next_month": {"start_date": "2026-06-01", "end_date": "2026-06-30"}, "month_after_next": {"start_date": "2026-07-01", "end_date": "2026-07-31"}, "next_next_month": {"start_date": "2026-07-01", "end_date": "2026-07-31"}}, "weekday_zh": "星期一"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "查询明天的公司会议安排。   当前问题含两个子目标：1）查询当前日期时间 → 使用 get_current_datetime；2）查询明天公司会议 → 使用 manage_company_calendar query`
- Answer preview: 当前日期：2026-05-18，时间：00:32:04，星期：星期一，时区：Asia/Shanghai。
2026-05-19 至 2026-05-19 没有匹配的公司日程。
