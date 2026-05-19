# Agent Evaluation Suite Report

- Generated at: `2026-05-17T15:08:03.021983+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 20 | 19 | 1 | 0.9500 | 7213.62 | 11442.79 |
| e2e | 20 | 19 | 1 | 0.9500 | 7213.62 | 11442.79 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 20 |
| executed_cases | 20 |
| infra_error_cases | 0 |
| agent_passed_cases | 19 |
| agent_failed_cases | 1 |
| agent_pass_rate | 0.95 |
| case_count | 20 |
| passed | 19 |
| failed | 1 |
| pass_rate | 0.95 |
| avg_latency_ms | 7213.62 |
| p95_latency_ms | 11442.79 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.65 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 0.95 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 0.95 |
| task_success | 0.95 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_v2_cal_query_003

- Question: 查下周所有公司团建日程。
- Failure reasons: task_success, expected_tool_coverage, refusal_accuracy, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 你没有权限修改公司日程，也无权执行该操作；当前角色权限不足。只有 admin 可以新增、更新或删除日程。
