# Retrieval Ablation Report

- Generated at: 2026-05-16 22:14:10
- Question file: `eval/rag_clean_eval_set/rag_long_kb_questions.jsonl`
- Question count: 0

## Summary

| Mode | Recall@K | Citation Hit Rate | Refusal Hit Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|
| vector_only | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.00 |
| hybrid_no_rerank | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.00 |
| hybrid_rerank | 0.0000 | 0.0000 | 0.0000 | 0.00 | 0.00 |

## How to explain this in an interview

- `vector_only` is the semantic retrieval baseline.
- `hybrid_no_rerank` adds BM25 keyword recall and RRF fusion, which helps entity names, product modules and exact policy terms.
- `hybrid_rerank` adds cross-encoder-like semantic ordering with Qwen rerank; it may improve evidence quality but increases latency and depends on external API stability.

## Per-case Details

### vector_only


### hybrid_no_rerank


### hybrid_rerank

