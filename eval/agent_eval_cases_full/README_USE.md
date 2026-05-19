# Agent Eval Case Set

This package contains evaluation cases for the unified `scripts/agent_eval_suite.py` runner.

## Files

- `rag_eval_questions.jsonl`: 32 RAG retrieval/answer cases
- `tool_eval_cases.jsonl`: 40 tool-calling trace cases
- `agent_e2e_eval_cases.jsonl`: 20 end-to-end Agent cases
- `all_eval_cases.jsonl`: all suites combined with a `suite` field
- `EVAL_CASES_README.md`: human-readable version

## Suggested commands

```bash
python scripts/agent_eval_suite.py \
  --suite rag \
  --questions eval/agent_eval_cases_full/rag_eval_questions.jsonl \
  --judge rule \
  --mode hybrid \
  --output outputs/eval/rag_suite

python scripts/agent_eval_suite.py \
  --suite tool \
  --questions eval/agent_eval_cases_full/tool_eval_cases.jsonl \
  --judge rule \
  --output outputs/eval/tool_suite

python scripts/agent_eval_suite.py \
  --suite e2e \
  --questions eval/agent_eval_cases_full/agent_e2e_eval_cases.jsonl \
  --judge both \
  --output outputs/eval/e2e_suite
```

## Notes

- RAG cases use `.md`, `.txt`, and `.docx` expected sources only.
- Tool and E2E cases are designed for trace-based checking.
- Write operations should be executed with per-case backup/restore in the eval runner.
- Some event IDs such as `cal_20260521_001` are intentionally deterministic placeholders. If your seeded calendar uses different IDs, update those exact-event cases or let the query-first cases be the primary benchmark.
