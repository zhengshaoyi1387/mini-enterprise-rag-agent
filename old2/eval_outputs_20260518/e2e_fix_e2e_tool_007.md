# Agent Evaluation Suite Report

- Generated at: `2026-05-16T17:59:07.296588+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 1 | 0 | 1 | 0.0000 | 12062.06 | 12062.06 |
| e2e | 1 | 0 | 1 | 0.0000 | 12062.06 | 12062.06 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| case_count | 1 |
| passed | 0 |
| failed | 1 |
| pass_rate | 0.0 |
| avg_latency_ms | 12062.06 |
| p95_latency_ms | 12062.06 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.0 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_tool_coverage | 0.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 0.0 |
| task_success | 0.0 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_tool_007

- Question: 删除 2099-01-01 的所有公司会议。
- Failure reasons: task_success, expected_tool_coverage, answer_must_contain_hit, refusal_accuracy, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 请说明具体要修改哪一个公司日程，例如提供 event_id、会议标题和日期，或先查询后指定第几个；在目标明确前我不会执行修改或删除。
