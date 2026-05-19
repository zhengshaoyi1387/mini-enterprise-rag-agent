# 使用说明

## 直接运行 RAG 评测

```bash
python scripts/agent_eval_suite.py \
  --suite rag \
  --questions eval/rag_long_kb_eval_set/rag_long_kb_questions.jsonl \
  --judge rule \
  --output outputs/eval/rag_long_report
```

如需切换检索模式：

```bash
python scripts/agent_eval_suite.py \
  --suite rag \
  --questions eval/rag_long_kb_eval_set/rag_long_kb_questions.jsonl \
  --mode hybrid_rerank \
  --judge rule \
  --limit 5 \
  --output outputs/eval/rag_long_smoke
```

## 字段说明

- `question`：统一评测脚本读取的主问题字段。
- `expected_sources`：规则评测会用它计算 source recall 和 citation hit。
- `should_refuse`：无证据问题设为 true，用来测拒答。
- `expected_answer_points`：LLM-as-judge 模式会参考它判断答案覆盖度，也适合人工复盘。
- `query / role / kb_ids / expected_kbs`：兼容你已有 enterprise 风格问题文件，普通 RAG eval 会忽略。

## 重要限制

当前源码的 `src/mini_rag/ingestion/loaders.py` 只支持 `.md`、`.markdown`、`.txt`、`.pdf`、`.docx`。因此这份主评测集没有把 `.json` / `.yaml` / `.csv` 文件作为期望来源。等你后面加了结构化文件 loader，再单独补一组结构化文件评测会更公平。
