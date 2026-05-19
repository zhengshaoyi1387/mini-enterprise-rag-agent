# Agent Evaluation Suite Report

- Generated at: `2026-05-16T19:23:25.376318+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 1 | 0 | 1 | 0.0000 | 160121.29 | 160121.29 |
| e2e | 1 | 0 | 1 | 0.0000 | 160121.29 | 160121.29 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| case_count | 1 |
| passed | 0 |
| failed | 1 |
| pass_rate | 0.0 |
| avg_latency_ms | 160121.29 |
| p95_latency_ms | 160121.29 |
| actual_success_no_blocked_tasks | 0.0 |
| answer_must_contain_hit | 0.0 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_tool_coverage | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 0.0 |
| task_success | 0.0 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_v2_cal_update_005

- Question: 把 2026-05-18 的会议改到 10 点。
- Failure reasons: task_success, answer_must_contain_hit, refusal_accuracy, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "把 2026-05-18 的会议改到 10 点。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询2026-05-18的会议", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司日程：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B，event_id：EVT-20260518-0001）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C，event_id：EVT-20260518-0002）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}]}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "将2026-05-18的会议时间修改为10点", "status": "needs_clarification", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "date": "2026-05-18", "time": "10:00", "selector": {"event_type": "meeting", "date": "2026-05-18"}}, "result_summary": "匹配到多个日程，请指定要更新的 event_id 后再修改。", "tool_result": {"status": "needs_clarification", "action": "update", "message": "匹配到多个日程，请指定要更新的 event_id 后再修改。"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据已完成的查询，2026-05-18（星期一）当天有两场会议：

- **10:00-11:00**：产品部 OKR 同步会（会议室 B，event_id：EVT-20260518-0001）  
- **14:00-15:00**：研发部周会（会议室 C，event_id：EVT-20260518-0002）

您希望将“2026-05-18 的会议改到 10 点”，但系统检测到当天存在多个会议，无法自动判断要修改哪一场。

请明确指定要修改的会议对应的 **event_id**（例如 EVT-20260518-0001 或 EVT-20260518-0002），以便完成时间调整。
