# Agent Evaluation Suite Report

- Generated at: `2026-05-17T12:31:58.757081+00:00`
- Suite: `rag`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 8 | 7 | 1 | 0.8750 | 14618.42 | 18208.54 |
| rag | 8 | 7 | 1 | 0.8750 | 14618.42 | 18208.54 |

## Metrics By Suite

### rag

| Metric | Value |
|---|---:|
| total_cases | 8 |
| executed_cases | 8 |
| infra_error_cases | 0 |
| agent_passed_cases | 7 |
| agent_failed_cases | 1 |
| agent_pass_rate | 0.875 |
| case_count | 8 |
| passed | 7 |
| failed | 1 |
| pass_rate | 0.875 |
| avg_latency_ms | 14618.42 |
| p95_latency_ms | 18208.54 |
| citation_hit | 0.875 |
| recall_at_k_hit | 0.875 |
| refusal_hit | 1.0 |

## Failed Cases

### rag / rag_clean_007

- Question: 根据《考勤与休假管理制度 2026》，连续病假超过 3 个工作日需要上传什么材料？事假超过 2 天需要哪些审批？
- Failure reasons: expected source not retrieved, expected source not cited in final answer
- Retrieved sources: hr/hr_03_compensation_benefits_faq.txt, hr/hr_02_performance_okr_manager_handbook.docx
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 根据《考勤与休假管理制度 2026》的相关说明：

- **连续病假超过 3 个工作日**：需上传**医疗证明**。  
- **事假超过 2 天**：需经过**直属负责人和 HRBP 双审批**。

引用来源：  
- source: hr/hr_03_compensation_benefits_faq.txt, title_path: hr_03_compensation_benefits_faq.txt, chunk_id: d9436d4dd08b:chunk:0213:a7911cdf  
- source: hr/hr_03_compensation_benefits_faq.txt, title_path: hr_03_compensation_benefits_faq.txt, chunk_id: d9436d4dd08b:chunk:0205:745dabcb
