# Agent Evaluation Suite Report

- Generated at: `2026-05-16T18:32:08.306051+00:00`
- Suite: `e2e`
- Judge: `both`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 10 | 2 | 0.8333 | 14570.78 | 20627.68 |
| e2e | 12 | 10 | 2 | 0.8333 | 14570.78 | 20627.68 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| case_count | 12 |
| passed | 10 |
| failed | 2 |
| pass_rate | 0.8333 |
| avg_latency_ms | 14570.78 |
| p95_latency_ms | 20627.68 |
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
| task_success | 0.9167 |
| write_result_success | 1.0 |
| llm_answer_correctness | 1.0 |
| llm_answer_completeness | 1.0 |
| llm_groundedness | 1.0 |
| llm_refusal_correctness | 1.0 |
| llm_task_success | 0.8333 |
| llm_hallucination_rate | 0.0 |

## Failed Cases

### e2e / e2e_tool_007

- Question: 删除 2099-01-01 的所有公司会议。
- Failure reasons: task_success, answer_must_contain_hit, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "删除 2099-01-01 的所有公司会议。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2099-01-01 的所有会议事件", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2099-01-01 至 2099-01-01 暂无公司日程。", "tool_result": {"action": "query", "events": []}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "删除上一步查询到的所有会议事件", "status": "skipped", "tool_name": "manage_company_calendar", "action": "delete", "tool_input": {"action": "delete", "selector": {"date": "2099-01-01", "event_type": "meeting"}}, "result_summary": "没有匹配日程可删除，无需删除。", "tool_result": {"status": "skipped", "action": "delete", "message": "没有匹配日程可删除，无需删除。"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，2099-01-01 当天没有安排任何公司会议，因此无需执行删除操作。

### e2e / e2e_tool_011

- Question: 把那个会议改成 10 点。
- Failure reasons: answer_must_contain_hit
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询当前日程中所有会议，以便定位需修改的会议", "status": "error", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "event_type": "meeting", "department": "all"}, "result_summary": "工具调用失败：tool_input_validation_failed", "tool_result": {"error": "tool_input_validation_failed", "message": "1 validation error for CalendarInput\n  Value error, query requires start_date and end_date [type=value_error, input_value={'action': 'query', 'even... None, 'end_date': None}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/value_error"}, "source_count": 0, "error_message": "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"}]`
- Answer preview: 要将会议时间修改为 10 点，首先需要明确是哪一场会议。但当前查询日程的工具调用因缺少起止日期（start_date 和 end_date）而失败，无法列出会议供你确认。

请提供会议的大致日期范围（例如“今天”“本周”或具体日期），以便先查出相关会议，再进行修改。
