# Agent Evaluation Suite Report

- Generated at: `2026-05-17T12:29:11.060472+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 20 | 19 | 1 | 0.9500 | 11447.82 | 18022.77 |
| e2e | 20 | 19 | 1 | 0.9500 | 11447.82 | 18022.77 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 20 |
| executed_cases | 19 |
| infra_error_cases | 1 |
| agent_passed_cases | 19 |
| agent_failed_cases | 0 |
| agent_pass_rate | 1.0 |
| case_count | 20 |
| passed | 19 |
| failed | 1 |
| pass_rate | 0.95 |
| avg_latency_ms | 11447.82 |
| p95_latency_ms | 18022.77 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.9474 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 1.0 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 1.0 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_v2_time_001

- Question: 现在上海时间是多少？顺便告诉我今天星期几。
- Failure reasons: infra_error, case execution error: Connection error.
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 
