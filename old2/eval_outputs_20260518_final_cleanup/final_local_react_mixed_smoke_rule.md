# Agent Evaluation Suite Report

- Generated at: `2026-05-18T13:00:27.812477+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 6 | 2 | 4 | 0.3333 | 17476.28 | 27881.78 |
| e2e | 6 | 2 | 4 | 0.3333 | 17476.28 | 27881.78 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 6 |
| executed_cases | 6 |
| infra_error_cases | 0 |
| agent_passed_cases | 2 |
| agent_failed_cases | 4 |
| agent_pass_rate | 0.3333 |
| case_count | 6 |
| passed | 2 |
| failed | 4 |
| pass_rate | 0.3333 |
| avg_latency_ms | 17476.28 |
| p95_latency_ms | 27881.78 |
| failure_categories | {'passed': 2, 'agent_answer_error': 2, 'agent_resolver_error': 2} |
| actual_success_no_blocked_tasks | 0.6667 |
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
| refusal_accuracy | 0.6667 |
| task_success | 0.3333 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / local_react_smoke_002_calendar_rag

- Question: 我明天有会议吗？如果有，出差报销回来要注意什么？
- Failure reasons: task_success, refusal_accuracy, grounded_answer_rate, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "我明天有会议吗？如果有，出差报销回来要注意什么？", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "出差报销回来注意事项", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "我明天有会议吗？如果有，出差报销回来要注意什么？", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天是否有会议", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司会议安排：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）", "tool_result": {"events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}], "action": "query"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "rag", "objective": "查询出差报销回来的注意事项", "status": "empty", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}]`
- Answer preview: 当前可访问知识库未找到明确依据，不能可靠回答该知识库部分。

### e2e / local_react_smoke_004_explain_event_id_all

- Question: 删除下周所有团建之前，先告诉我为什么不能直接 event_id=all。
- Failure reasons: task_success, refusal_accuracy, actual_success=false
- Retrieved sources: finance/finance_03_budget_cost_marketing_cloud_policy.txt, product/product_03_tool_calling_trace_observability.txt
- Tool calls: `[{"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "为什么不能直接用 event_id=all 删除下周所有团建", "kb_ids": ["finance", "hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "系统限制使用 event_id=all 删除日程的政策依据或技术原因", "kb_ids": ["finance", "hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "系统限制使用 event_id=all 删除日程的技术设计原则或权限控制策略", "kb_ids": ["finance", "hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "rag", "objective": "解释为什么系统不允许使用 event_id=all 删除日程", "status": "empty", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}, {"task_id": "t2", "kind": "rag", "objective": "解释为什么系统不允许使用 event_id=all 删除日程", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}, {"task_id": "t3", "kind": "rag", "objective": "解释为什么系统不允许使用 event_id=all 删除日程", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}]`
- Answer preview: 当前可访问知识库未找到明确依据，不能可靠回答该知识库部分。

### e2e / local_react_smoke_005_query_first_update_ordinal

- Question: 把下周第一个团建地点改到多功能厅，改完告诉我结果。
- Failure reasons: task_success, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "type_filtered", "event_type": "activity", "department": "all", "query": "把下周第一个团建地点改到多功能厅，改完告诉我结果。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "type_filtered", "event_type": "activity", "department": "all", "query": "把下周第一个团建地点改到多功能厅，改完告诉我结果。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "manage_company_calendar", "action": "update", "args": {"action": "update", "event_id": "EVT-20260519-0001", "location": "多功能厅", "query": "把下周第一个团建地点改到多功能厅，改完告诉我结果。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询下周第一个团建活动", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "type_filtered", "event_type": "activity", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-24 的公司日程：\n- 2026-05-19 星期二 16:00-18:00 公司团建（城市公园）\n- 2026-05-21 星期四 18:00-20:00 公司团建（团建餐厅）", "tool_result": {"events": [{"event_id": "EVT-20260519-0001", "date": "2026-05-19", "title": "公司团建", "type": "activity", "department": "all", "time": "16:00-18:00", "location": "城市公园", "description": "下周第一个团建活动，用于 update/delete 评测", "weekday_zh": "星期二"}, {"event_id": "EVT-20260521-0002", "date": "2026-05-21", "title": "公司团建", "type": "activity", "department": "all", "time": "18:00-20:00", "location": "团建餐厅", "description": "第二个团建活动", "weekday_zh": "星期四"}], "action": "query"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "更新第一个团建活动地点为多功能厅", "status": "skipped", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "location": "多功能厅", "selector": {"event_id": "t1_result.event_id"}}, "result_summary": "没有匹配日程可更新。", "tool_result": {"message": "没有匹配日程可更新。", "status": "skipped", "action": "update"}, "source_count": 0, "error_message": ""}, {"task_id": "t3", "kind": "tool", "objective": "重新查询下周第一个团建活动以确认是否存在", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24`
- Answer preview: 2026-05-18 至 2026-05-24 的公司日程：
- 2026-05-19 星期二 16:00-18:00 公司团建（城市公园）
- 2026-05-21 星期四 18:00-20:00 公司团建（团建餐厅）
没有匹配日程可更新。
公司日程已更新：2026-05-19 星期二 16:00-18:00 公司团建（多功能厅）。

### e2e / local_react_smoke_006_question_not_update

- Question: 能不能把明天会议改到 10 点？
- Failure reasons: task_success, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "能不能把明天会议改到 10 点？", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天的会议事件以获取 event_id", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司会议安排：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）", "tool_result": {"events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}], "action": "query"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "更新明天会议时间为 10:00", "status": "needs_clarification", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "selector": {"event_type": "meeting", "date": "tomorrow"}, "time": "10:00-10:00"}, "result_summary": "匹配到多个日程，请指定要更新的 event_id 后再修改。", "tool_result": {"message": "匹配到多个日程，请指定要更新的 event_id 后再修改。", "status": "needs_clarification", "action": "update"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 我还需要更具体的信息才能继续处理，请补充目标、日期或标识。
