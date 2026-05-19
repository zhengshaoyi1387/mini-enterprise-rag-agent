# Agent Evaluation Suite Report

- Generated at: `2026-05-17T14:27:13.802939+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 10 | 2 | 0.8333 | 10506.38 | 12017.67 |
| e2e | 12 | 10 | 2 | 0.8333 | 10506.38 | 12017.67 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 12 |
| executed_cases | 12 |
| infra_error_cases | 0 |
| agent_passed_cases | 10 |
| agent_failed_cases | 2 |
| agent_pass_rate | 0.8333 |
| case_count | 12 |
| passed | 10 |
| failed | 2 |
| pass_rate | 0.8333 |
| avg_latency_ms | 10506.38 |
| p95_latency_ms | 12017.67 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.8333 |
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
| task_success | 0.8333 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_tool_006

- Question: 查询明天公司会议安排，然后告诉我能不能删除它。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "查询明天公司会议安排，然后告诉我能不能删除它。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天公司会议安排", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司会议安排：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}]}, "source_count": 0, "error_message": ""}]`
- Answer preview: 2026-05-18 至 2026-05-18 的公司会议安排：
- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）
- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）

### e2e / e2e_tool_007

- Question: 删除 2099-01-01 的所有公司会议。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "删除 2099-01-01 的所有公司会议。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2099-01-01 的所有公司会议事件 ID", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2099-01-01 至 2099-01-01 暂无公司日程。", "tool_result": {"action": "query", "events": []}, "source_count": 0, "error_message": ""}]`
- Answer preview: 2099-01-01 至 2099-01-01 暂无公司日程。
