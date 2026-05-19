# Agent Evaluation Suite Report

- Generated at: `2026-05-18T13:10:05.678524+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 6 | 5 | 1 | 0.8333 | 14743.86 | 28870.66 |
| e2e | 6 | 5 | 1 | 0.8333 | 14743.86 | 28870.66 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 6 |
| executed_cases | 6 |
| infra_error_cases | 0 |
| agent_passed_cases | 5 |
| agent_failed_cases | 1 |
| agent_pass_rate | 0.8333 |
| case_count | 6 |
| passed | 5 |
| failed | 1 |
| pass_rate | 0.8333 |
| avg_latency_ms | 14743.86 |
| p95_latency_ms | 28870.66 |
| failure_categories | {'passed': 5, 'agent_answer_error': 1} |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 1.0 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 1.0 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 0.8333 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 0.8333 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / local_react_smoke_002_calendar_rag

- Question: 我明天有会议吗？如果有，出差报销回来要注意什么？
- Failure reasons: task_success, grounded_answer_rate, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "我明天有会议吗？如果有，出差报销回来要注意什么？", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "出差报销回来要注意什么", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "我明天有会议吗？如果有，出差报销回来要注意什么？", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天是否有会议", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司会议安排：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}]}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "rag", "objective": "查询出差报销回来的注意事项", "status": "empty", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}]`
- Answer preview: 2026-05-18 至 2026-05-18 的公司会议安排：
- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）
- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）

关于查询出差报销回来的注意事项：当前可访问知识库未找到明确依据，不能可靠回答该知识库部分。
