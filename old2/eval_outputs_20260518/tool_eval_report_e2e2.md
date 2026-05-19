# Agent Evaluation Suite Report

- Generated at: `2026-05-16T16:18:29.511377+00:00`
- Suite: `tool`
- Judge: `both`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 10 | 2 | 0.8333 | 17451.22 | 26342.41 |
| tool | 12 | 10 | 2 | 0.8333 | 17451.22 | 26342.41 |

## Metrics By Suite

### tool

| Metric | Value |
|---|---:|
| case_count | 12 |
| passed | 10 |
| failed | 2 |
| pass_rate | 0.8333 |
| avg_latency_ms | 17451.22 |
| p95_latency_ms | 26342.41 |
| action_accuracy | 1.0 |
| answer_must_contain_hit | 0.5833 |
| answer_must_not_contain_pass | 0.9167 |
| argument_accuracy | 1.0 |
| forbidden_argument_pass | 1.0 |
| permission_accuracy | 0.9167 |
| route_accuracy | 1.0 |
| tool_accuracy | 1.0 |
| tool_sequence_accuracy | 1.0 |
| write_safety | 1.0 |
| write_verification | 1.0 |
| llm_answer_correctness | 0.75 |
| llm_answer_completeness | 0.75 |
| llm_groundedness | 1.0 |
| llm_refusal_correctness | 1.0 |
| llm_task_success | 0.5833 |
| llm_hallucination_rate | 0.0833 |

## Failed Cases

### tool / e2e_tool_007

- Question: 删除 2099-01-01 的所有公司会议。
- Failure reasons: answer_must_not_contain_pass
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "all", "department": "all", "query": "删除 2099-01-01 的所有公司会议。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "manage_company_calendar", "action": "delete", "args": {"action": "delete", "event_id": "multiple", "query": "删除 2099-01-01 的所有公司会议。", "user_id": "eval_user", "role": "admin"}, "ok": false, "error": "event not found", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2099-01-01 的所有公司会议事件以获取 event_id", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2099-01-01", "end_date": "2099-01-01", "query_scope": "all_events", "event_type": "all", "department": "all"}, "result_summary": "2099-01-01 至 2099-01-01 暂无公司日程。", "tool_result": {"events": [], "action": "query"}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "删除查询到的 2099-01-01 的所有公司会议事件", "status": "error", "tool_name": "manage_company_calendar", "action": "delete", "tool_input": {"action": "delete", "event_id": "multiple"}, "result_summary": "工具调用失败：event not found", "tool_result": {"error": "event not found", "action": "delete", "event_id": "multiple"}, "source_count": 0, "error_message": "工具执行失败，请检查请求参数后再试。"}]`
- Answer preview: 根据工具查询结果：

1. **查询 2099-01-01 的公司会议**  
   工具返回：2099-01-01 至 2099-01-01 暂无公司日程。说明该日期下不存在任何公司会议事件。

2. **删除 2099-01-01 的公司会议**  
   工具调用失败，报错“event not found”，这与上一步查询结果一致——因无对应事件，无法执行删除操作。

综上，2099-01-01 当日没有公司会议，因此无需也**无法删除**任何会议。

### tool / e2e_tool_011

- Question: 把那个会议改成 10 点。
- Failure reasons: permission_accuracy
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 我没有能力或权限直接修改会议时间。请通过日历应用（如 Outlook、钉钉日程或企业微信日程）手动调整，或联系会议组织者/行政助理协助更改。
