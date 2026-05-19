# Agent Evaluation Suite Report

- Generated at: `2026-05-17T17:22:54.635088+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 1 | 0 | 1 | 0.0000 | 0.00 | 0.00 |
| e2e | 1 | 0 | 1 | 0.0000 | 0.00 | 0.00 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 1 |
| executed_cases | 0 |
| infra_error_cases | 1 |
| agent_passed_cases | 0 |
| agent_failed_cases | 0 |
| agent_pass_rate | 0.0 |
| case_count | 1 |
| passed | 0 |
| failed | 1 |
| pass_rate | 0.0 |
| avg_latency_ms | 0.0 |
| p95_latency_ms | 0.0 |
| failure_categories | {'infra_error': 1} |

## Failed Cases

### e2e / e2e_v2_time_001

- Question: 现在上海时间是多少？顺便告诉我今天星期几。
- Failure reasons: infra_error, case execution error: Error code: 403 - {'error': {'message': 'The free tier of the model has been exhausted. If you wish to continue access the model on a paid basis, please disable the "use free tier only" mode in the management console.', 'type': 'AllocationQuota.FreeTierOnly', 'param': None, 'code': 'AllocationQuota.FreeTierOnly'}, 'id': 'chatcmpl-47879ffa-61c4-950a-baef-210a874090c5', 'request_id': '47879ffa-61c4-950a-baef-210a874090c5'}
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 
