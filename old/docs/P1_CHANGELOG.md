# P1 优化变更记录

本阶段目标：在 P0 工程化基础上补齐评测闭环、检索 ablation、请求日志和面试材料。

## 新增能力

1. 新增 `mini_rag.evaluation.metrics`
   - `recall_at_k`
   - `citation_hit_rate`
   - `refusal_hit_rate`
   - `avg_latency_ms`
   - `p95_latency_ms`

2. 新增检索 ablation
   - `scripts/retrieval_ablation.py`
   - `src/mini_rag/evaluation/retrieval_ablation.py`
   - 对比 vector_only / hybrid_no_rerank / hybrid_rerank

3. 增强 `scripts/eval.py`
   - 输出 JSON 报告
   - 输出 Markdown 报告
   - 新增 p95 latency

4. 新增受保护评测接口
   - `POST /eval/run`
   - 仅 admin 可访问
   - 支持 `rag_eval` 和 `retrieval_ablation`

5. 新增网关请求日志
   - `logs/requests.jsonl`
   - 记录 request_id、method、path、status_code、latency_ms
   - 不记录 body，避免泄漏用户问题或密钥

6. 新增测试集
   - `eval/p1_quality_questions.jsonl`
   - `eval/ablation_questions.jsonl`

7. 新增文档
   - `EVAL_REPORT.md`
   - `RETRIEVAL_ABLATION.md`
   - `FAILURE_CASES.md`

## 新增测试

- `tests/test_evaluation_metrics.py`
- `tests/test_eval_endpoint_auth.py`
- `tests/test_request_logger.py`
