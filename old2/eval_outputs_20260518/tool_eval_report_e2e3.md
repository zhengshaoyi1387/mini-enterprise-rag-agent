# Agent Evaluation Suite Report

- Generated at: `2026-05-16T17:14:43.924784+00:00`
- Suite: `tool`
- Judge: `both`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 8 | 4 | 0.6667 | 17313.57 | 21090.02 |
| tool | 12 | 8 | 4 | 0.6667 | 17313.57 | 21090.02 |

## Metrics By Suite

### tool

| Metric | Value |
|---|---:|
| case_count | 12 |
| passed | 8 |
| failed | 4 |
| pass_rate | 0.6667 |
| avg_latency_ms | 17313.57 |
| p95_latency_ms | 21090.02 |
| action_accuracy | 1.0 |
| answer_must_contain_hit | 0.5 |
| answer_must_not_contain_pass | 1.0 |
| argument_accuracy | 1.0 |
| forbidden_argument_pass | 1.0 |
| permission_accuracy | 0.9167 |
| route_accuracy | 1.0 |
| tool_accuracy | 1.0 |
| tool_sequence_accuracy | 1.0 |
| write_safety | 1.0 |
| write_verification | 1.0 |
| llm_answer_correctness | 1.0 |
| llm_answer_completeness | 0.8333 |
| llm_groundedness | 1.0 |
| llm_refusal_correctness | 1.0 |
| llm_task_success | 0.6667 |
| llm_hallucination_rate | 0.0 |

## Failed Cases

### tool / e2e_tool_001

- Question: 先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。
- Failure reasons: llm judge task_success=0, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2024-06-17", "end_date": "2024-06-23", "query_scope": "all_events", "event_type": "activity", "department": "all", "query": "先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询下周所有公司团建日程", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2024-06-17", "end_date": "2024-06-23", "query_scope": "all_events", "event_type": "activity", "department": "all"}, "result_summary": "2024-06-17 至 2024-06-23 暂无公司日程。", "tool_result": {"events": [], "action": "query"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "将查询到的第一个团建日程更新为公司高层会议（21:00-22:00，会议室A）", "status": "skipped", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "selector": {"event_type": "activity", "ordinal": 1}, "title": "公司高层会议", "time": "21:00-22:00", "location": "会议室A", "type": "meeting"}, "result_summary": "没有匹配日程可更新。", "tool_result": {"status": "skipped", "action": "update", "message": "没有匹配日程可更新。"}, "source_count": 0, "error_message": ""}]`
- Answer preview: ### 一、下周公司团建日程查询结果  
根据工具查询结果，2024年6月17日（周一）至2024年6月23日（周日）期间，公司日历中**暂无任何团建日程安排**。

### 二、关于修改第一个团建日程为高层会议的操作  
由于查询结果为空，**不存在可被识别和修改的“第一个团建日程”**，因此无法执行更新操作。工具返回提示：“没有匹配日程可更新”。

如需新增公司高层会议，请提供具体日期（如2024-06-XX），我可协助创建；或确认是否需在其他时间段（如再下周）查询团建日程后再操作。

### tool / e2e_tool_003

- Question: 删除明天的公司会议。
- Failure reasons: permission_accuracy, llm judge task_success=0, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 你没有权限修改公司日程。只有 admin 可以新增、更新或删除日程。

### tool / e2e_tool_006

- Question: 查询明天公司会议安排，然后告诉我能不能删除它。
- Failure reasons: llm judge task_success=0, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天公司会议安排", "status": "error", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "event_type": "meeting", "department": "all", "start_date": "", "end_date": ""}, "result_summary": "工具调用失败：tool_input_validation_failed", "tool_result": {"error": "tool_input_validation_failed", "message": "1 validation error for CalendarInput\n  Value error, query requires start_date and end_date [type=value_error, input_value={'action': 'query', 'star...te': '', 'end_date': ''}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error"}, "source_count": 0, "error_message": "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"}]`
- Answer preview: 根据当前工具调用结果，查询明天公司会议安排失败，原因是 `manage_company_calendar.query` 工具缺少必需的 `start_date` 和 `end_date` 参数，无法执行检索。因此，既无法获取明天的会议信息，也无法判断该会议是否可以删除。

如需继续操作，请提供具体的日期范围（例如：`start_date="2024-06-15"`, `end_date="2024-06-15"`），我将重新尝试查询。另外请注意：删除会议属于写操作，当前角色权限仅支持 `query`，无权执行删除动作（需管理员权限）。

### tool / e2e_tool_011

- Question: 把那个会议改成 10 点。
- Failure reasons: llm judge task_success=0, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询当前日程中匹配“会议”的事件，以便定位要修改的会议", "status": "error", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "event_type": "meeting", "department": "all"}, "result_summary": "工具调用失败：tool_input_validation_failed", "tool_result": {"error": "tool_input_validation_failed", "message": "1 validation error for CalendarInput\n  Value error, query requires start_date and end_date [type=value_error, input_value={'action': 'query', 'even... None, 'end_date': None}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error"}, "source_count": 0, "error_message": "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"}, {"task_id": "t2", "kind": "tool", "objective": "根据查询结果，更新选定会议的时间为10点", "status": "skipped", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "selector": {"event_type": "meeting", "title": "模糊匹配或用户指定标题（需执行时确认）"}, "time": "10:00"}, "result_summary": "没有匹配日程可更新。", "tool_result": {"status": "skipped", "action": "update", "message": "没有匹配日程可更新。"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 无法将会议改为10点，原因如下：

1. **未能查询到匹配的会议**  
   尝试通过日程工具查询包含“会议”的事件，但因缺少 `start_date` 和 `end_date` 参数，导致查询失败（`tool_input_validation_failed`）。没有日期范围，系统无法定位具体哪一场会议。

2. **无法执行时间更新**  
   由于未成功查出目标会议（无 event_id），后续更新操作无法进行，工具返回“没有匹配日程可更新”。

✅ 解决方法：请提供会议发生的日期范围（例如“本周三到周五”或具体起止日期），我可据此重新查询并修改时间。
