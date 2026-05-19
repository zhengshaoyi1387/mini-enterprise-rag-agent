# Agent Evaluation Suite Report

- Generated at: `2026-05-17T12:40:16.523845+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 1 | 0 | 1 | 0.0000 | 29789.85 | 29789.85 |
| e2e | 1 | 0 | 1 | 0.0000 | 29789.85 | 29789.85 |

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
| avg_latency_ms | 29789.85 |
| p95_latency_ms | 29789.85 |
| actual_success_no_blocked_tasks | 0.0 |
| answer_must_contain_hit | 1.0 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 1.0 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 0.0 |
| task_success | 0.0 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_v2_cal_update_008

- Question: 把不存在的 event_id EVT-20990101-9999 改成测试会议。
- Failure reasons: task_success, refusal_accuracy, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "update", "args": {"action": "update", "event_id": "EVT-20990101-9999", "title": "测试会议", "query": "把不存在的 event_id EVT-20990101-9999 改成测试会议。", "user_id": "eval_user", "role": "admin"}, "ok": false, "error": "event not found", "purpose": null}, {"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}, {"tool_name": "manage_company_calendar", "action": "list", "args": {}, "ok": false, "error": "permission denied", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "更新事件：将 event_id EVT-20990101-9999 的标题改为‘测试会议’", "status": "error", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "event_id": "EVT-20990101-9999", "title": "测试会议"}, "result_summary": "工具调用失败：event not found", "tool_result": {"error": "event not found", "event_id": "EVT-20990101-9999", "action": "update"}, "source_count": 0, "error_message": "工具执行失败，请检查请求参数后再试。"}, {"task_id": "t2", "kind": "tool", "objective": "创建新事件：标题为‘测试会议’，event_id 自动分配或指定为 EVT-20990101-9999（若需保留该 ID）", "status": "error", "tool_name": "manage_company_calendar", "action": "create", "tool_input": {"action": "create", "title": "测试会议", "event_id": "EVT-20990101-9999"}, "result_summary": "工具调用失败：tool_input_validation_failed", "tool_result": {"error": "tool_input_validation_failed", "message": "1 validation error for CalendarInput\n  Value error, create requires time [type=value_error, input_value={'action': 'create', 'dat...d': 'EVT-20990101-9999'}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error"}, "source_count": 0, "error_message": "我还缺少执行该能力所需的必要信息，请补充具体日期、时间或事件信息。"}, {"task_id": "t3", "kind": "tool", "objective": "查询 calendar 中是否存在 event_id 为 EVT-20990101-9999 的事件，以确认其不存在或获取其详情", "status": "error", "tool_name": "manage_company_calendar", "action": "list", "tool_input": {"action": "list", "event_id": "EVT-20990101-9999"}, "result_summary": "工具调用失败：tool_input_validation_failed", "tool_result": {"error": "tool_input_validation_failed", "message": "1 validation e`
- Answer preview: 你当前角色没有权限使用该企业能力。
