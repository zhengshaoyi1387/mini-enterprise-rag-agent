# Agent Evaluation Suite Report

- Generated at: `2026-05-17T12:40:33.651907+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 1 | 0 | 1 | 0.0000 | 13674.56 | 13674.56 |
| e2e | 1 | 0 | 1 | 0.0000 | 13674.56 | 13674.56 |

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
| avg_latency_ms | 13674.56 |
| p95_latency_ms | 13674.56 |
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
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_v2_cal_delete_001

- Question: 删除 2099-01-01 的所有公司会议。
- Failure reasons: task_success, expected_tool_coverage, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "删除 2099-01-01 的所有公司会议。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2099-01-01 的所有公司会议事件 ID", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2099-01-01 至 2099-01-01 暂无公司日程。", "tool_result": {"events": [], "action": "query"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，2099-01-01 当天暂无公司日程，因此没有会议可删除。
