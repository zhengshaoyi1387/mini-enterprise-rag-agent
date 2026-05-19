# Agent Evaluation Suite Report

- Generated at: `2026-05-16T18:25:22.241576+00:00`
- Suite: `e2e`
- Judge: `both`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 10 | 2 | 0.8333 | 14538.47 | 20486.85 |
| e2e | 12 | 10 | 2 | 0.8333 | 14538.47 | 20486.85 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| case_count | 12 |
| passed | 10 |
| failed | 2 |
| pass_rate | 0.8333 |
| avg_latency_ms | 14538.47 |
| p95_latency_ms | 20486.85 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.8333 |
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
| llm_answer_correctness | 1.0 |
| llm_answer_completeness | 1.0 |
| llm_groundedness | 1.0 |
| llm_refusal_correctness | 1.0 |
| llm_task_success | 0.8333 |
| llm_hallucination_rate | 0.0 |

## Failed Cases

### e2e / e2e_tool_006

- Question: 查询明天公司会议安排，然后告诉我能不能删除它。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "查询明天公司会议安排，然后告诉我能不能删除它。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天公司会议安排", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司日程：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B，event_id：EVT-20260518-0001）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C，event_id：EVT-20260518-0002）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}]}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，明天（2026-05-18，星期一）有以下公司会议安排：

- 10:00-11:00：产品部 OKR 同步会（会议室 B，event_id：EVT-20260518-0001）  
- 14:00-15:00：研发部周会（会议室 C，event_id：EVT-20260518-0002）

关于能否删除这些会议：当前角色在 manage_company_calendar 工具中仅被授权执行 query 操作，**无权删除公司日程**。因此，你不能删除这些会议安排。

### e2e / e2e_tool_009

- Question: 把 event_id 为 EVT-20260522-0002 的日程改成客户复盘会，时间 16:00-17:00，地点会议室 C。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "update", "args": {"action": "update", "event_id": "EVT-20260522-0002", "title": "客户复盘会", "time": "16:00-17:00", "location": "会议室 C", "query": "把 event_id 为 EVT-20260522-0002 的日程改成客户复盘会，时间 16:00-17:00，地点会议室 C。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "更新指定 event_id 的日程信息", "status": "ok", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "event_id": "EVT-20260522-0002", "title": "客户复盘会", "time": "16:00-17:00", "location": "会议室 C"}, "result_summary": "公司日程已更新：2026-05-22 星期五 16:00-17:00 客户复盘会。", "tool_result": {"event_id": "EVT-20260522-0002", "message": "公司日程已更新", "action": "update", "event": {"event_id": "EVT-20260522-0002", "date": "2026-05-22", "title": "客户复盘会", "type": "meeting", "department": "销售部", "time": "16:00-17:00", "location": "会议室 C", "description": "固定 ID，用于更新为客户复盘会", "weekday_zh": "星期五"}, "status": "updated"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 公司日程已更新：2026-05-22 星期五 16:00-17:00 客户复盘会。
