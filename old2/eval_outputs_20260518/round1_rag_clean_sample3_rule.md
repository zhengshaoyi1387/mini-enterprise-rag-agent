# Agent Evaluation Suite Report

- Generated at: `2026-05-17T11:35:27.892728+00:00`
- Suite: `rag`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 3 | 2 | 1 | 0.6667 | 15761.06 | 17503.39 |
| rag | 3 | 2 | 1 | 0.6667 | 15761.06 | 17503.39 |

## Metrics By Suite

### rag

| Metric | Value |
|---|---:|
| total_cases | 3 |
| executed_cases | 3 |
| infra_error_cases | 0 |
| agent_passed_cases | 2 |
| agent_failed_cases | 1 |
| agent_pass_rate | 0.6667 |
| case_count | 3 |
| passed | 2 |
| failed | 1 |
| pass_rate | 0.6667 |
| avg_latency_ms | 15761.06 |
| p95_latency_ms | 17503.39 |
| citation_hit | 1.0 |
| recall_at_k_hit | 1.0 |
| refusal_hit | 0.6667 |

## Failed Cases

### rag / rag_clean_002

- Question: 根据《公司运营与协作手册 2026》，公司内部统一使用哪个入口作为正式制度入口？飞书或邮件截图能否替代正式制度链接？
- Failure reasons: refusal behavior mismatch
- Retrieved sources: public/public_01_company_operations_handbook_2026.md
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 根据《公司运营与协作手册 2026》，公司内部统一使用**星河协同门户**作为正式制度入口。**飞书或邮件中的截图不能替代正式制度链接**。

引用来源：  
- source: public/public_01_company_operations_handbook_2026.md  
  title_path: 公司运营与协作手册 2026 > 4. 关键规则与阈值  
  chunk_id: 12a3cac20f2f:chunk:0157:3fb03515  

- source: public/public_01_company_operations_handbook_2026.md  
  title_path: 公司运营与协作手册 2026 > 6. 场景案例 > 案例 3  
  chunk_id: 12a3cac20f2f:chunk:0161:fe49174d  

- source: public/public_01_company_operations_handbook_2026.md  
  title_path: 公司运营与协作手册 2026 > 6. 场景案例 > 案例 9  
  chunk_id: 12a3cac20f2f:chunk:0167:7a200aa0
