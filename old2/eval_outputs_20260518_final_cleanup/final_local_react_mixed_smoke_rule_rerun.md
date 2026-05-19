# Agent Evaluation Suite Report

- Generated at: `2026-05-18T13:07:10.705642+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 6 | 3 | 3 | 0.5000 | 15624.95 | 28683.52 |
| e2e | 6 | 3 | 3 | 0.5000 | 15624.95 | 28683.52 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 6 |
| executed_cases | 6 |
| infra_error_cases | 0 |
| agent_passed_cases | 3 |
| agent_failed_cases | 3 |
| agent_pass_rate | 0.5 |
| case_count | 6 |
| passed | 3 |
| failed | 3 |
| pass_rate | 0.5 |
| avg_latency_ms | 15624.95 |
| p95_latency_ms | 28683.52 |
| failure_categories | {'passed': 3, 'agent_answer_error': 3} |
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
| refusal_accuracy | 0.5 |
| task_success | 0.5 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / local_react_smoke_002_calendar_rag

- Question: 我明天有会议吗？如果有，出差报销回来要注意什么？
- Failure reasons: task_success, refusal_accuracy, grounded_answer_rate, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all", "query": "我明天有会议吗？如果有，出差报销回来要注意什么？", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "出差报销回来要注意什么", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "我明天有会议吗？如果有，出差报销回来要注意什么？", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天是否有会议", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "type_filtered", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司会议安排：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）", "tool_result": {"events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}], "action": "query"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "rag", "objective": "查询出差报销回来的注意事项", "status": "empty", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}]`
- Answer preview: 2026-05-18 至 2026-05-18 的公司会议安排：
- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）
- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）

关于查询出差报销回来的注意事项：当前可访问知识库未找到明确依据，不能可靠回答该知识库部分。

### e2e / local_react_smoke_004_explain_event_id_all

- Question: 删除下周所有团建之前，先告诉我为什么不能直接 event_id=all。
- Failure reasons: task_success, refusal_accuracy, actual_success=false
- Retrieved sources: finance/finance_02_invoice_payment_tax_controls.docx, product/product_03_tool_calling_trace_observability.txt
- Tool calls: `[{"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "为什么不能直接用 event_id=all 删除下周所有团建", "kb_ids": ["finance", "hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "系统限制使用 event_id=all 删除日程的原因，包括安全策略、数据完整性或权限控制相关规则", "kb_ids": ["finance", "hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "系统限制使用 event_id=all 删除日程的具体安全策略、权限控制或数据完整性规则，特别是与批量操作、审批流程或系统设计相关的限制", "kb_ids": ["finance", "hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "rag", "objective": "解释为什么系统不允许使用 event_id=all 删除日程", "status": "empty", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}, {"task_id": "t2", "kind": "rag", "objective": "解释为什么系统不允许使用 event_id=all 删除日程", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}, {"task_id": "t3", "kind": "rag", "objective": "解释为什么系统不允许使用 event_id=all 删除日程", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}]`
- Answer preview: 不能直接使用 event_id=all 执行日程删除或更新。真实写工具只接受具体的 EVT-YYYYMMDD-0001 这类单个 event_id；all、multiple、event_id_from_x 这类占位符必须先经过查询和 selector 解析，确认 0 个、1 个、多个或“全部/所有”的明确范围。在目标未解析成真实 event_id 前，我不会执行删除。

### e2e / local_react_smoke_006_question_not_update

- Question: 能不能把明天会议改到 10 点？
- Failure reasons: task_success, refusal_accuracy, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 请说明具体要修改哪一个公司日程，例如提供 event_id、会议标题和日期，或先查询后指定第几个；在目标明确前我不会执行修改或删除。
