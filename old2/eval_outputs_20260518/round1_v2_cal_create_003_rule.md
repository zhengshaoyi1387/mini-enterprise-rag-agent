# Agent Evaluation Suite Report

- Generated at: `2026-05-17T11:34:29.433053+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 1 | 0 | 1 | 0.0000 | 9542.07 | 9542.07 |
| e2e | 1 | 0 | 1 | 0.0000 | 9542.07 | 9542.07 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 1 |
| executed_cases | 1 |
| infra_error_cases | 0 |
| agent_passed_cases | 0 |
| agent_failed_cases | 1 |
| agent_pass_rate | 0.0 |
| case_count | 1 |
| passed | 0 |
| failed | 1 |
| pass_rate | 0.0 |
| avg_latency_ms | 9542.07 |
| p95_latency_ms | 9542.07 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.0 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_tool_coverage | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 0.0 |
| task_success | 0.0 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_v2_cal_create_003

- Question: 创建一个公司会议。
- Failure reasons: task_success, refusal_accuracy, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 请说明具体要修改哪一个公司日程，例如提供 event_id、会议标题和日期，或先查询后指定第几个；在目标明确前我不会执行修改或删除。
