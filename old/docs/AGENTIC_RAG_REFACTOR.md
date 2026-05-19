# Agentic RAG + LangGraph 重构说明

本版本重构目标：保留原有文档加载、切分、Chroma、hybrid retrieval、Qwen rerank 能力，推倒重写 Agent 编排层。

## 新链路

```text
load_context
  -> understand_query      # LLM：上下文理解、追问消解、intent/topic/entities
  -> route                 # LLM：direct / rag / tool / reject
  -> plan_retrieval        # LLM：生成结构化 search_tasks
  -> retrieve              # 工具：执行 hybrid retrieval + rerank
  -> reflect_evidence      # LLM：证据是否足够，必要时建议 followup_tasks
  -> retrieve              # LangGraph 最多补检索 1 次
  -> generate_answer       # LLM：基于证据和评估生成最终回答
  -> update_memory         # LLM：写入干净 memory_answer
```

## 关键设计

- LLM 负责理解、规划、反思、生成。
- LangGraph 负责流程控制、循环边界、状态隔离。
- 代码只负责结构化解析、执行工具、去重、记忆清洗、trace。
- `session_id` 只用于业务会话记忆；`workflow_run_id` 用于本轮 LangGraph 运行，避免旧 State 污染。
- 记忆中区分：
  - `answer`：展示给用户的完整答案，可包含引用。
  - `memory_answer`：下一轮上下文理解用的干净答案，不包含 source/title_path/chunk_id。
  - `trace`：仅排查问题使用，不参与下一轮语义理解。

## 新增目录

```text
src/mini_rag/graph/
├── state.py       # AgentState
├── utils.py       # JSON 解析、元数据清洗、证据格式化
├── prompts.py     # Agentic RAG 各节点提示词
├── nodes.py       # LangGraph 节点实现
└── workflow.py    # LangGraph 编排入口
```

## 主要替换

- `src/mini_rag/agent/graph_agent.py` 已替换为新 workflow 的适配器。
- `src/mini_rag/agent/context_store.py` 增加 `memory_answer / intent / topic / entities` 字段，并兼容旧 SQLite 表自动迁移。

## 建议测试

```bash
python scripts/ask.py "你是什么模型" --session-id demo001
python scripts/ask.py "什么版本的" --session-id demo001
python scripts/ask.py "智能客服平台包含哪些核心模块" --session-id demo002
python scripts/ask.py "介绍一下这些模块" --session-id demo002
python scripts/ask.py "介绍一下前三个模块" --session-id demo002
```

如果之前本地已有脏状态，建议先清理：

```bash
rm -f storage/context.sqlite3 storage/langgraph_checkpoints.sqlite3
```
