# Agent Evaluation Suite Report

- Generated at: `2026-05-17T11:17:28.370331+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 20 | 18 | 2 | 0.9000 | 14893.92 | 20732.41 |
| e2e | 20 | 18 | 2 | 0.9000 | 14893.92 | 20732.41 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| case_count | 20 |
| passed | 18 |
| failed | 2 |
| pass_rate | 0.9 |
| avg_latency_ms | 14893.92 |
| p95_latency_ms | 20732.41 |
| actual_success_no_blocked_tasks | 0.9 |
| answer_must_contain_hit | 0.9 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_tool_coverage | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 0.9 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_v2_cal_query_008

- Question: 先告诉我今天日期，再查明天的会议和后天的培训。
- Failure reasons: task_success, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai", "query": "先告诉我今天日期，再查明天的会议和后天的培训。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "${tomorrow}", "end_date": "${tomorrow}", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "先告诉我今天日期，再查明天的会议和后天的培训。", "user_id": "eval_user", "role": "employee"}, "ok": false, "error": "invalid date format", "purpose": null}, {"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "${day_after_tomorrow}", "end_date": "${day_after_tomorrow}", "query_scope": "all_events", "event_type": "training", "department": "all", "query": "先告诉我今天日期，再查明天的会议和后天的培训。", "user_id": "eval_user", "role": "employee"}, "ok": false, "error": "invalid date format", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "获取当前日期", "status": "ok", "tool_name": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}, "result_summary": "当前日期：2026-05-17，时间：19:15:37，星期：Sunday，时区：Asia/Shanghai。", "tool_result": {"ranges": {"today": {"start_date": "2026-05-17", "end_date": "2026-05-17"}, "yesterday": {"start_date": "2026-05-16", "end_date": "2026-05-16"}, "tomorrow": {"start_date": "2026-05-18", "end_date": "2026-05-18"}, "day_after_tomorrow": {"start_date": "2026-05-19", "end_date": "2026-05-19"}, "this_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"}, "last_week": {"start_date": "2026-05-04", "end_date": "2026-05-10"}, "next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}, "week_after_next": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "next_next_week": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "this_month": {"start_date": "2026-05-01", "end_date": "2026-05-31"}, "last_month": {"start_date": "2026-04-01", "end_date": "2026-04-30"}, "next_month": {"start_date": "2026-06-01", "end_date": "2026-06-30"}, "month_after_next": {"start_date": "2026-07-01", "end_date": "2026-07-31"}, "next_next_month": {"start_date": "2026-07-01", "end_date": "2026-07-31"}}, "weekday_zh": "星期日", "timezone": "Asia/Shanghai", "current_time": "19:15:37", "current_date": "2026-05-17", "weekday": "Sunday"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "查询明天的会议", "status": "error", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"acti`
- Answer preview: 根据已完成的任务和工具结果，回答如下：

### 1. 今天日期  
今天是 **2026年5月17日（星期日）**。

### 2. 明天的会议  
未能查询到明天（2026年5月18日，星期一）的会议安排。原因：工具调用时因日期格式错误失败，当前未获得有效结果。

### 3. 后天的培训  
未能查询到后天（2026年5月19日，星期二）的培训安排。原因：同样因日期格式错误导致工具调用失败，当前未获得有效结果。

如需继续查询，请确保使用正确的日期格式重新尝试。

### e2e / e2e_v2_cal_create_003

- Question: 创建一个公司会议。
- Failure reasons: task_success, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "创建一个公司会议", "status": "error", "tool_name": "manage_company_calendar", "action": "create", "tool_input": {"action": "create", "title": "公司会议", "type": "meeting", "department": "all"}, "result_summary": "工具调用失败：tool_input_validation_failed", "tool_result": {"error": "tool_input_validation_failed", "message": "1 validation error for CalendarInput\n  Value error, create requires date [type=value_error, input_value={'action': 'create', 'tit...ent': 'all', 'date': ''}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error"}, "source_count": 0, "error_message": "我还缺少执行该能力所需的必要信息，请补充具体日期、时间或事件信息。"}]`
- Answer preview: 创建公司会议需要提供具体的日期等必要信息。当前尝试因缺少日期字段而失败。请补充会议的标题、日期、时间、地点等详细信息后重试。
