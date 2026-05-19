# Agent Evaluation Suite Report

- Generated at: `2026-05-16T18:20:38.382597+00:00`
- Suite: `e2e`
- Judge: `both`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 10 | 2 | 0.8333 | 13923.75 | 17906.13 |
| e2e | 12 | 10 | 2 | 0.8333 | 13923.75 | 17906.13 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| case_count | 12 |
| passed | 10 |
| failed | 2 |
| pass_rate | 0.8333 |
| avg_latency_ms | 13923.75 |
| p95_latency_ms | 17906.13 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 1.0 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_tool_coverage | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 1.0 |
| write_result_success | 1.0 |
| llm_answer_correctness | 1.0 |
| llm_answer_completeness | 1.0 |
| llm_groundedness | 1.0 |
| llm_refusal_correctness | 1.0 |
| llm_task_success | 0.8333 |
| llm_hallucination_rate | 0.0 |

## Failed Cases

### e2e / e2e_tool_003

- Question: 删除明天的公司会议。
- Failure reasons: llm judge task_success=0, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 你没有权限修改公司日程，也无权执行该操作；当前角色权限不足。只有 admin 可以新增、更新或删除日程。

### e2e / e2e_tool_011

- Question: 把那个会议改成 10 点。
- Failure reasons: llm judge task_success=0, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 请说明具体要修改哪一个公司日程，例如提供 event_id、会议标题和日期，或先查询后指定第几个；在目标明确前我不会执行修改或删除。
