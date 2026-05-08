# Eval 评测闭环说明

本项目提供轻量但可解释的评测闭环，重点服务于面试展示和迭代优化。

## 评测集

推荐使用：

```bash
eval/p1_quality_questions.jsonl
```

其中包含：

1. 制度类关键词问题
2. 产品文档语义问题
3. 多文档对比问题
4. 多轮追问问题
5. 知识库无答案拒答问题
6. 安全拒答问题
7. Agent Infra 面试口述题
8. 检索链路原理题

## 运行方式

```bash
python scripts/eval.py
```

或通过受保护接口运行：

```bash
curl -X POST http://127.0.0.1:8000/eval/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -H "X-User-Role: admin" \
  -d '{"mode":"rag_eval","questions_path":"eval/p1_quality_questions.jsonl"}'
```

## 输出

```text
eval/runs/eval_YYYYMMDD_HHMMSS.json
eval/runs/eval_YYYYMMDD_HHMMSS.md
```

## 指标

| 指标 | 说明 |
|---|---|
| recall_at_k | 检索结果是否命中期望来源 |
| citation_hit_rate | 回答是否引用期望来源 |
| refusal_hit_rate | 应拒答问题是否拒答 |
| avg_latency_ms | 平均响应延迟 |
| p95_latency_ms | 长尾延迟 |

## 面试表达模板

> 我没有只跑单条 demo，而是把问题分成制度类、产品类、多文档对比、多轮追问和无答案拒答几类。每次迭代后跑评测，观察 recall、citation、refusal 和 latency。这样可以定位到底是召回问题、引用问题、拒答问题，还是性能问题。
