# Agent Evaluation Suite Report

- Generated at: `2026-05-17T12:22:31.345103+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 20 | 19 | 1 | 0.9500 | 14183.04 | 21072.51 |
| e2e | 20 | 19 | 1 | 0.9500 | 14183.04 | 21072.51 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 20 |
| executed_cases | 20 |
| infra_error_cases | 0 |
| agent_passed_cases | 19 |
| agent_failed_cases | 1 |
| agent_pass_rate | 0.95 |
| case_count | 20 |
| passed | 19 |
| failed | 1 |
| pass_rate | 0.95 |
| avg_latency_ms | 14183.04 |
| p95_latency_ms | 21072.51 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.9 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 0.95 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 0.95 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_v2_cal_query_008

- Question: 先告诉我今天日期，再查明天的会议和后天的培训。
- Failure reasons: task_success, expected_tool_coverage, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai", "query": "先告诉我今天日期，再查明天的会议和后天的培训。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "先告诉我今天日期，再查明天的会议和后天的培训", "status": "ok", "tool_name": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}, "result_summary": "当前日期：2026-05-17，时间：20:20:58，星期：Sunday，时区：Asia/Shanghai。", "tool_result": {"weekday": "Sunday", "ranges": {"today": {"start_date": "2026-05-17", "end_date": "2026-05-17"}, "yesterday": {"start_date": "2026-05-16", "end_date": "2026-05-16"}, "tomorrow": {"start_date": "2026-05-18", "end_date": "2026-05-18"}, "day_after_tomorrow": {"start_date": "2026-05-19", "end_date": "2026-05-19"}, "this_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"}, "last_week": {"start_date": "2026-05-04", "end_date": "2026-05-10"}, "next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}, "week_after_next": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "next_next_week": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "this_month": {"start_date": "2026-05-01", "end_date": "2026-05-31"}, "last_month": {"start_date": "2026-04-01", "end_date": "2026-04-30"}, "next_month": {"start_date": "2026-06-01", "end_date": "2026-06-30"}, "month_after_next": {"start_date": "2026-07-01", "end_date": "2026-07-31"}, "next_next_month": {"start_date": "2026-07-01", "end_date": "2026-07-31"}}, "current_date": "2026-05-17", "current_time": "20:20:58", "timezone": "Asia/Shanghai", "weekday_zh": "星期日"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 今天是 2026 年 5 月 17 日，星期日。

根据当前可执行的操作权限，我只能查询公司日程，但未实际调用日程查询工具获取明天（2026-05-18，星期一）的会议和后天（2026-05-19，星期二）的培训安排。因此，目前没有获得这两日的具体日程信息。
