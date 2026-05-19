# Agent Evaluation Suite Report

- Generated at: `2026-05-16T18:05:35.079544+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 9 | 3 | 0.7500 | 17227.47 | 24559.39 |
| e2e | 12 | 9 | 3 | 0.7500 | 17227.47 | 24559.39 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| case_count | 12 |
| passed | 9 |
| failed | 3 |
| pass_rate | 0.75 |
| avg_latency_ms | 17227.47 |
| p95_latency_ms | 24559.39 |
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
| task_success | 0.75 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_tool_006

- Question: 查询明天公司会议安排，然后告诉我能不能删除它。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "查询明天公司会议安排，然后告诉我能不能删除它。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天公司会议安排", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司日程：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B，event_id：EVT-20260518-0001）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C，event_id：EVT-20260518-0002）", "tool_result": {"events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}], "action": "query"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，明天（2026-05-18，星期一）公司有以下会议安排：

- 10:00-11:00：产品部 OKR 同步会（会议室 B，event_id：EVT-20260518-0001）  
- 14:00-15:00：研发部周会（会议室 C，event_id：EVT-20260518-0002）

关于能否删除这些会议：当前角色在日程管理工具中仅具备 **query（查询）** 权限，**无权删除公司日程**。

### e2e / e2e_tool_007

- Question: 删除 2099-01-01 的所有公司会议。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "删除 2099-01-01 的所有公司会议。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2099-01-01 的所有公司会议事件", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2099-01-01 至 2099-01-01 暂无公司日程。", "tool_result": {"events": [], "action": "query"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "删除上一步查询返回的会议事件", "status": "skipped", "tool_name": "manage_company_calendar", "action": "delete", "tool_input": {"action": "delete", "selector": {"date": "2099-01-01", "event_type": "meeting"}}, "result_summary": "没有匹配日程可删除，无需删除。", "tool_result": {"status": "skipped", "action": "delete", "message": "没有匹配日程可删除，无需删除。"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，2099-01-01 当天没有安排任何公司会议，因此无需执行删除操作。系统已确认该日期无相关日程，原始请求已完整处理完毕。

### e2e / e2e_tool_008

- Question: 现在的日期时间是多少？顺便查一下明天的公司会议安排。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai", "query": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-17", "end_date": "2026-05-17", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "获取当前日期和时间", "status": "ok", "tool_name": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}, "result_summary": "当前日期：2026-05-17，时间：02:04:25，星期：Sunday，时区：Asia/Shanghai。", "tool_result": {}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "查询明天的公司会议安排", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-17", "end_date": "2026-05-17", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-17 至 2026-05-17 的公司日程：\n- 2026-05-17 星期日 08:00-10:00 公司会议（会议室，event_id：EVT-20260517-0001）", "tool_result": {"events": [{"event_id": "EVT-20260517-0001", "date": "2026-05-17", "title": "公司会议", "type": "meeting", "department": "all", "time": "08:00-10:00", "location": "会议室", "description": "公司会议", "weekday_zh": "星期日"}], "action": "query"}, "source_count": 0, "error_message": ""}]`
- Answer preview: ### 当前日期时间  
当前日期：2026-05-17，时间：02:04:25，星期日，时区：Asia/Shanghai。

### 明天的公司会议安排  
根据工具查询结果，明天（2026-05-18）没有公司会议安排。  

> 注：已查询的公司日程仅包含 2026-05-17（星期日）当天的一场会议（08:00-10:00，会议室），未返回 2026-05-18 的任何日程。
