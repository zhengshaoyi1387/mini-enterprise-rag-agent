# Agent Evaluation Suite Report

- Generated at: `2026-05-16T17:53:08.631048+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 9 | 3 | 0.7500 | 17683.42 | 24889.75 |
| e2e | 12 | 9 | 3 | 0.7500 | 17683.42 | 24889.75 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| case_count | 12 |
| passed | 9 |
| failed | 3 |
| pass_rate | 0.75 |
| avg_latency_ms | 17683.42 |
| p95_latency_ms | 24889.75 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.75 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_tool_coverage | 1.0 |
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
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "查询明天公司会议安排，然后告诉我能不能删除它。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天公司会议安排", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司日程：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B，event_id：EVT-20260518-0001）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C，event_id：EVT-20260518-0002）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}]}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，明天（2026-05-18，星期一）公司有以下会议安排：

- 10:00-11:00：产品部 OKR 同步会（会议室 B，event_id：EVT-20260518-0001）  
- 14:00-15:00：研发部周会（会议室 C，event_id：EVT-20260518-0002）

关于“能不能删除它”：当前你的角色仅具备日程查询权限（manage_company_calendar 的 query 权限），没有删除或修改日程的权限。因此，你无法删除这些会议安排。

### e2e / e2e_tool_007

- Question: 删除 2099-01-01 的所有公司会议。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "删除 2099-01-01 的所有公司会议。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2099-01-01 的所有公司会议事件", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2099-01-01 至 2099-01-01 暂无公司日程。", "tool_result": {"action": "query", "events": []}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "根据查询结果删除匹配的会议事件", "status": "skipped", "tool_name": "manage_company_calendar", "action": "delete", "tool_input": {"action": "delete", "selector": {"date": "2099-01-01", "event_type": "meeting"}}, "result_summary": "没有匹配日程可删除。", "tool_result": {"message": "没有匹配日程可删除", "status": "skipped", "action": "delete"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，2099-01-01 当天没有公司会议安排，因此无需执行删除操作。系统已确认该日期无任何日程，原始请求的目标已达成。

### e2e / e2e_tool_011

- Question: 把那个会议改成 10 点。
- Failure reasons: answer_must_contain_hit
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}, {"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询当前日程中匹配“会议”的事件，获取可更新的 event_id", "status": "error", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "event_type": "meeting", "department": "all"}, "result_summary": "工具调用失败：tool_input_validation_failed", "tool_result": {"message": "1 validation error for CalendarInput\n  Value error, query requires start_date and end_date [type=value_error, input_value={'action': 'query', 'even... None, 'end_date': None}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error", "error": "tool_input_validation_failed"}, "source_count": 0, "error_message": "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"}, {"task_id": "t2", "kind": "tool", "objective": "更新找到的会议事件时间为10点", "status": "skipped", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "event_id": "<placeholder>", "new_start_time": "10:00"}, "result_summary": "没有匹配日程可更新。", "tool_result": {"message": "没有匹配日程可更新。", "status": "skipped", "action": "update"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据已完成的工具调用结果：

1. **查询会议事件失败**：在尝试查询当前日程中匹配“会议”的事件时，工具因缺少必要的 `start_date` 和 `end_date` 参数而验证失败，未能返回任何事件或 event_id。

2. **更新会议时间未执行成功**：由于上一步未找到可操作的会议事件，后续更新时间为10点的操作也未能成功，系统反馈“没有匹配日程可更新”。

因此，目前无法完成将会议改为10点的操作。建议提供具体的日期范围（如“今天”或“本周一至周五”），以便重新查询并定位需要修改的会议。
