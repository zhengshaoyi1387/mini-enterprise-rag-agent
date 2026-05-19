# Agent Evaluation Suite Report

- Generated at: `2026-05-17T14:23:28.466964+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 1 | 0 | 1 | 0.0000 | 31807.98 | 31807.98 |
| e2e | 1 | 0 | 1 | 0.0000 | 31807.98 | 31807.98 |

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
| avg_latency_ms | 31807.98 |
| p95_latency_ms | 31807.98 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.0 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 1.0 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 0.0 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_tool_008

- Question: 现在的日期时间是多少？顺便查一下明天的公司会议安排。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai", "query": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询现在的日期时间，并查看明天的公司会议安排。", "status": "ok", "tool_name": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}, "result_summary": "当前日期：2026-05-17，时间：22:23:28，星期：星期日，时区：Asia/Shanghai。", "tool_result": {"weekday": "Sunday", "weekday_zh": "星期日", "timezone": "Asia/Shanghai", "current_date": "2026-05-17", "ranges": {"today": {"start_date": "2026-05-17", "end_date": "2026-05-17"}, "yesterday": {"start_date": "2026-05-16", "end_date": "2026-05-16"}, "tomorrow": {"start_date": "2026-05-18", "end_date": "2026-05-18"}, "day_after_tomorrow": {"start_date": "2026-05-19", "end_date": "2026-05-19"}, "this_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"}, "last_week": {"start_date": "2026-05-04", "end_date": "2026-05-10"}, "next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}, "week_after_next": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "next_next_week": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "this_month": {"start_date": "2026-05-01", "end_date": "2026-05-31"}, "last_month": {"start_date": "2026-04-01", "end_date": "2026-04-30"}, "next_month": {"start_date": "2026-06-01", "end_date": "2026-06-30"}, "month_after_next": {"start_date": "2026-07-01", "end_date": "2026-07-31"}, "next_next_month": {"start_date": "2026-07-01", "end_date": "2026-07-31"}}, "current_time": "22:23:28"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "查询明天的公司会议安排。   复合请求包含日期查询与日程查询，均需调用工具处理公司日程", "status": "ok", "tool_name": "manage_company_cal`
- Answer preview: 当前日期：2026-05-17，时间：22:23:28，星期：星期日，时区：Asia/Shanghai。
2026-05-18 至 2026-05-18 的公司日程：
- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）
- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）
