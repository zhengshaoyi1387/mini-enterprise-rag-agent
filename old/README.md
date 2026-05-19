# Old Versions Archive

这个目录保存项目重构过程中下线的旧入口、旧说明和旧评测产物。它们不再属于当前主线，也不会被 pytest 主测试集递归执行。

当前主线保留在项目根目录：

- LangGraph 企业 Agent：`src/mini_rag/agent/agent.py`、`src/mini_rag/agent/graph_agent.py`、`src/mini_rag/graph/`
- 统一评测脚本：`scripts/agent_eval_suite.py`
- 当前评测用例：`eval/agent_eval_cases_full/`、`eval/rag_clean_eval_set/rag_clean_questions.jsonl`
- 当前文档：`README.md`、`ARCHITECTURE.md`、`SECURITY.md`、`INTERVIEW_GUIDE.md`、`EVALUATION_SUITE_GUIDE.md`

归档内容包括：

- `old/scripts/`：旧 `scripts/eval.py` 和 `scripts/retrieval_ablation.py`
- `old/src/mini_rag/eval.py`：旧 RAG-only 评测入口
- `old/src/mini_rag/evaluation/retrieval_ablation.py`：旧检索 ablation runner
- `old/src/mini_rag/agent/`：旧脚本式 Agent、旧 context/router/retrieval/reflection helper
- `old/src/mini_rag/prompts/agent.py`：旧 helper prompt 集合
- `old/tests/`：依赖旧 helper 的测试
- `old/docs/`：P0/P1、旧优化、旧评测和过渡期说明文档
- `old/eval/`：旧 RAG/Agent 问题集、旧兼容问题集、旧 eval 报告和旧 retrieval ablation 报告

如需参考旧实现，可以直接阅读这些文件；如需恢复运行，应手动移回并同时恢复对应 imports。当前项目不会再从 `old/` 导入代码。
