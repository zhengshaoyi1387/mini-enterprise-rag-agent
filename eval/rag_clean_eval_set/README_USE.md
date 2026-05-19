# RAG Clean Eval Set

这是一版针对“已删除污染源文件”后的 RAG 评测问题集。

## 文件

- `rag_clean_questions.jsonl`：主版本，包含扩展字段，可直接跑当前统一评测，也方便后续人工分析。
- `rag_clean_questions.md`：人工阅读版。
- `SOURCE_COVERAGE.csv`：source 覆盖情况。
- `MANIFEST.json`：生成摘要。

## 设计原则

1. 不包含 `RAG_EVAL_SEED_QUESTIONS.md`、README、MANIFEST 等污染源。
2. 只使用你当前 loader 支持的 `.md / .txt / .docx` 作为 expected source。
3. 问题中显式点名文档标题，减少合成知识库里重复条款导致的 source 误判。
4. 32 条问题：30 条有证据问答 + 2 条无证据拒答。
5. 每条都包含 `expected_answer_points`，当前自动评测不会读取，但适合人工看答案忠实度。

## 推荐用法

```bash
python scripts/agent_eval_suite.py \
  --suite rag \
  --questions eval/rag_clean_eval_set/rag_clean_questions.jsonl \
  --judge rule \
  --output outputs/eval/rag_clean_report
```

如果只想快速抽样：

```bash
python scripts/agent_eval_suite.py \
  --suite rag \
  --questions eval/rag_clean_eval_set/rag_clean_questions.jsonl \
  --judge rule \
  --limit 5 \
  --output outputs/eval/rag_clean_smoke
```

## 注意

当前项目的 `citation_hit` 要求 `expected_sources` 里的所有文件名都出现在答案中；所以这版没有把“可接受替代来源”直接塞进 `expected_sources`，避免引入额外假失败。
