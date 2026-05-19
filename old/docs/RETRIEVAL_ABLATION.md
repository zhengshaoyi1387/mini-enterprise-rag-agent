# Retrieval Ablation 设计说明

本项目不是只声称“用了混合检索”，而是提供可运行的 ablation 脚本，用相同问题集对比不同检索策略的质量和延迟。

## 对比模式

| 模式 | 配置 | 目标 |
|---|---|---|
| vector_only | `retrieval_mode=vector, enable_rerank=false` | 纯语义检索 baseline |
| hybrid_no_rerank | `retrieval_mode=hybrid, enable_rerank=false` | 验证 BM25 + RRF 对关键词/实体词的提升 |
| hybrid_rerank | `retrieval_mode=hybrid, enable_rerank=true` | 验证 rerank 对最终证据排序的影响 |

## 运行方式

```bash
python scripts/retrieval_ablation.py --questions eval/p1_quality_questions.jsonl
```

运行后会生成：

```text
eval/runs/retrieval_ablation_YYYYMMDD_HHMMSS.json
eval/runs/retrieval_ablation_YYYYMMDD_HHMMSS.md
```

## 指标解释

- `recall_at_k`：期望来源是否出现在检索结果中。
- `citation_hit_rate`：最终答案是否引用了期望来源。
- `refusal_hit_rate`：无答案/安全风险问题是否被拒答。
- `avg_latency_ms`：平均耗时。
- `p95_latency_ms`：长尾耗时，用于定位线上体验风险。

## 面试表达模板

> 我做了 vector-only、hybrid-no-rerank、hybrid-rerank 三组 ablation。vector-only 是语义召回 baseline；hybrid 用 BM25 覆盖制度名、产品模块名、参数名等关键词，再用 RRF 融合不同通道排名；rerank 进一步重排候选证据。评估时不只看召回，还看 citation hit rate、refusal hit rate 和 latency，因为真实 Agent 系统需要在质量、成本和延迟之间取舍。
