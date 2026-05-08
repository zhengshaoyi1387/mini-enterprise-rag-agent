# Mini Enterprise RAG Agent

> P0 面试工程化版本：新增 FastAPI Gateway `/chat`、API Key 鉴权、user_id/role、endpoint/tool 权限、trace_id 与 `/traces/{trace_id}`。详见 `ARCHITECTURE.md`、`SECURITY.md`、`INTERVIEW_GUIDE.md`、`API_TESTING.md`。

## P0 快速启动与接口测试

```bash
cp .env.example .env
# 填写 DASHSCOPE_API_KEY；本地开发默认 AGENT_API_KEY=dev-api-key
python scripts/build_index.py --reset
python scripts/serve.py
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

新的工程化 `/chat` 接口：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -d '{
    "user_id": "u001",
    "role": "user",
    "query": "智能客服平台有哪些核心模块？",
    "session_id": "demo-session",
    "retrieval_mode": "hybrid",
    "enable_rerank": true
  }'
```

返回中的 `trace_id` 可由 admin 查询：

```bash
curl http://127.0.0.1:8000/traces/<trace_id> \
  -H "X-API-Key: dev-api-key" \
  -H "X-User-Role: admin"
```

---

## P1：90 分项目增强能力

本版本在 P0 的 `/chat`、鉴权、权限和 trace 基础上，继续补齐面试高价值能力：

- `POST /eval/run`：admin 受保护评测接口。
- `scripts/retrieval_ablation.py`：对比 `vector_only`、`hybrid_no_rerank`、`hybrid_rerank`。
- `eval/p1_quality_questions.jsonl`：覆盖制度、产品、多文档、多轮、拒答、安全和面试口述题。
- `logs/requests.jsonl`：网关级请求日志，不记录 body，避免泄漏敏感内容。
- `EVAL_REPORT.md`、`RETRIEVAL_ABLATION.md`、`FAILURE_CASES.md`：用于面试展示的评测、检索取舍和失败案例材料。

运行 RAG 评测：

```bash
EVAL_QUESTIONS_PATH=eval/p1_quality_questions.jsonl python scripts/eval.py
```

运行检索 ablation：

```bash
python scripts/retrieval_ablation.py --questions eval/p1_quality_questions.jsonl
```

通过 API 触发评测：

```bash
curl -X POST http://127.0.0.1:8000/eval/run \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -H "X-User-Role: admin" \
  -d '{"mode":"retrieval_ablation","questions_path":"eval/p1_quality_questions.jsonl"}'
```

---


> 已重构为 Agentic RAG + LangGraph 编排版本。详见 `AGENTIC_RAG_REFACTOR.md`。

核心特点：LLM 负责理解/规划/反思/生成，LangGraph 负责状态流转和循环控制，SQLite 只保存干净业务记忆，trace 只用于排查。

---

# Mini Enterprise RAG Agent

这是一个**面向新手学习和实习面试展示**的企业知识库 Agent 项目。项目基于现代 LangChain 框架，模型统一使用 Qwen / 阿里云百炼 OpenAI 兼容接口，向量库使用本地 Chroma。

项目重点不是“大而全”，而是把企业知识库 Agent 的核心链路讲清楚、跑通、可调试：

```text
企业文档目录
  ↓
LangChain DirectoryLoader 加载 .md / .txt / .pdf / .docx
  ↓
MarkdownHeaderTextSplitter 按 Markdown 标题结构切分
  ↓
RecursiveCharacterTextSplitter 二次切 chunk
  ↓
Qwen3-Embedding / text-embedding-v4 向量化
  ↓
增量索引 manifest + Chroma 本地向量库
  ↓
向量检索 + BM25 + RRF + Qwen qwen3-rerank
  ↓
少量真实企业工具：知识库检索 / 当前时间 / 考勤 CSV / 公司日程 JSON
  ↓
LangGraph 状态机 Agent：load_context -> manage_context -> llm_router -> execute_tool -> reflect -> final
  ↓
LLM 检索规划：单问题单 query，多模块问题拆成多个子 query
  ↓
LLM 证据评估：证据不足时生成 followup query 继续检索
  ↓
Qwen 基于证据和评估生成带引用答案，并持久化上下文
  ↓
Trace 记录检索、工具、LLM、总耗时
```

## 1. 项目特性

- **LangGraph 状态机 Agent**：默认使用显式节点编排，保留 legacy `create_agent` 对比路径。
- **文档加载采用常用官方组合**：使用 `DirectoryLoader` 加载 Markdown、TXT、PDF、Word。
- **增量索引**：通过 `storage/index_manifest.json` 记录文件 hash 和 chunk ids，只更新变更文件。
- **Markdown 结构化切分**：使用 `MarkdownHeaderTextSplitter` 保留标题层级，生成 `title_path`。
- **二次 chunk 切分**：使用 `RecursiveCharacterTextSplitter` 控制 chunk 大小。
- **Qwen 系列模型**：聊天模型默认 `qwen-plus`，Embedding 默认 `text-embedding-v4`。
- **混合检索与重排**：向量检索 + BM25 + RRF 融合，并默认调用 Qwen `qwen3-rerank` 做二次排序。
- **本地向量库**：使用 Chroma 持久化到 `storage/chroma`。
- **Agent 工具调用**：不堆砌 prompt wrapper，只保留 `search_knowledge_base`、`get_current_datetime`、`query_attendance_summary`、`manage_company_calendar` 这 4 个真实、有边界的企业日常工具。
- **LLM Router**：由 Qwen 输出结构化 route，并用 JSON 校验和危险关键词兜底。
- **LLM 上下文管理**：由 Qwen 维护会话摘要、选择相关历史、生成独立检索问题。
- **LLM 检索规划**：需要检索时由 Qwen 判断是否拆成多个子查询，分别召回证据。
- **LLM 证据评估**：每轮检索后由 Qwen 判断证据是否足够，不足时生成补充检索 query。
- **集中提示词目录**：所有阶段提示词集中在 `src/mini_rag/prompts/`，便于逐条审查和调优。
- **SQLite 多轮会话**：支持 `session_id` 持久化上下文，服务重启后仍可追问。
- **引用溯源**：回答要求引用 `source`、`title_path`、`chunk_id`。
- **延迟观测**：每次问答可保存 trace JSON，便于分析性能瓶颈。
- **CLI + FastAPI**：支持命令行问答和 Web API。

## 2. 企业日常助手工具

本项目不是堆砌大量 prompt wrapper 工具，而是保留少量真实、有边界的企业日常工具：

- `search_knowledge_base`：查询非结构化企业知识库。
- `get_current_datetime`：获取当前日期时间，辅助解析“今天、昨天、上周、下周、本月”等相对时间。
- `query_attendance_summary`：读取本地 CSV，统计结构化考勤数据。
- `manage_company_calendar`：读取/写入本地 JSON 公司日程，普通成员只读，admin 可写。

工具示例问题：

1. 查制度：“公司的迟到规则是什么？” -> RAG / `search_knowledge_base`
2. 查考勤：“上周公司的出勤情况怎么样？” -> `get_current_datetime` -> `query_attendance_summary`
3. 查日程：“下周公司有哪些安排？” -> `get_current_datetime` -> `manage_company_calendar(action=query)`
4. 管理员写日程：“帮我添加下周三下午两点的新员工培训。” -> `get_current_datetime` -> `manage_company_calendar(action=create)`，只有 admin 允许。
5. 普通用户写日程：“帮我添加一个公司会议。” -> 权限不足，拒绝写入。

## 3. 安装

推荐使用虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

复制环境变量模板：

```bash
cp .env.example .env
```

编辑 `.env`，至少填入：

```bash
DASHSCOPE_API_KEY=你的百炼APIKey
```

## 3. 准备文档

把企业知识库文档放到：

```text
data/raw/
```

当前项目默认支持：

```text
.md
.markdown
.txt
.pdf
.docx
```

示例文件已经放在 `data/raw/` 下面，可以直接测试。

## 4. 构建索引

```bash
python scripts/build_index.py --reset
```

或者使用安装后的命令：

```bash
mini-rag build-index --reset
```

这一步默认是增量构建；只有发生变化的文件会重新切分和写入。`--reset` 会删除旧 Chroma 后全量重建。

这一步会：

1. 用 LangChain `DirectoryLoader` 扫描 `data/raw`。
2. 用 `TextLoader` / `PyPDFLoader` / `Docx2txtLoader` 读取 Markdown / TXT / PDF / Word 文件。
3. 用 `MarkdownHeaderTextSplitter` 按标题切 Markdown。
4. 用 `RecursiveCharacterTextSplitter` 做二次 chunk。
5. 用 Qwen Embedding 模型生成向量。
6. 删除变更文件的旧 chunk，写入新 chunk，并更新 `storage/index_manifest.json`。

## 5. Agent 问答

```bash
python scripts/ask.py "智能客服平台包含哪些核心模块"
```

或：

```bash
mini-rag ask "智能客服平台包含哪些核心模块" --retrieval-mode hybrid
mini-rag ask "它有哪些模块？" --session-id demo-session
mini-rag ask "智能客服平台包含哪些核心模块" --no-rerank
```

默认 Agent runtime 是 LangGraph：

```bash
AGENT_RUNTIME=langgraph
```

质量优先的性能参数：

```bash
# 最终回答模型仍由 QWEN_CHAT_MODEL 控制；控制节点模型默认不单独降级。
QWEN_CONTROL_MODEL=
AGENT_ENABLE_RETRIEVAL_CACHE=true
AGENT_MAX_SEARCH_TASKS=3
AGENT_MAX_FOLLOWUP_TASKS=2
AGENT_REFLECT_MAX_ROUNDS=2
AGENT_EVIDENCE_CHAR_LIMIT=2200
```

这组参数保留 hybrid 检索、Qwen rerank 和最终回答质量，同时让 LLM 自己决定整体检索、细分检索或混合检索；代码只限制浪费，默认初始检索最多 3 个 query、每轮补检索最多 2 个 query，并压缩进入 LLM 的证据上下文。Trace 中会额外记录 `total_latency_ms`、`llm_calls`、`retrieval_cache_hit`、`rerank_cache_hit`、`skipped_reflection_reason`。

如果想和旧版脚本式 Agent 对比，可以在 `.env` 中设置：

```bash
AGENT_RUNTIME=legacy
```

默认使用 Agent 版本。Agent 的提示词集中在 `src/mini_rag/prompts/`。核心要求：

- Router 自己判断是否需要检索，不机械调用知识库。
- 多模块、多对象问题进入检索规划阶段拆成多个子查询。
- 每轮检索后由证据评估阶段判断是否足够回答。
- 最终回答只能基于工具返回的证据和证据评估。
- 证据不足时说明缺少哪部分信息。
- 回答必须标注来源。

## 6. 启动 API 服务

```bash
python scripts/serve.py
```

或：

```bash
mini-rag serve
```

请求示例：

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"智能客服平台包含哪些核心模块","use_agent":true,"session_id":"demo","retrieval_mode":"hybrid","enable_rerank":true}'
```

## 7. 评测闭环

项目内置一个轻量评测入口，读取 `eval/questions.jsonl`，输出到 `eval/runs/`：

```bash
mini-rag eval
# 或
python scripts/eval.py
```

报告包含：

- `recall_at_k`：期望来源是否被检索到。
- `citation_hit_rate`：答案是否包含期望引用来源。
- `refusal_hit_rate`：应拒答问题是否明确说证据不足。
- `avg_latency_ms`：平均问答延迟。

## 8. 企业级增强点

第一阶段增强：

- 支持 PDF / Word 企业文档。
- 增量索引避免每次全量重建。
- 混合检索提升关键词和语义召回。
- Qwen rerank 提升最终证据排序质量，失败时自动降级。
- Eval 报告让检索质量可以量化展示。

第三阶段增强：

- LangGraph 状态机 Agent：显式拆分 load_context、manage_context、llm_router、execute_tool、reflect、final、persist_context。
- LLM Router：模型决定 rag/tool/direct/reject，危险请求强制 reject。
- LLM Context Manager：模型维护 summary、选择相关历史、生成 standalone query。
- LLM Retrieval Planner：模型决定是否把一个问题拆成多个检索 query。
- LLM Evidence Reflector：每轮检索后判断证据是否足够，不足时补充检索。
- `session_id` SQLite 多轮会话：能演示服务重启后的连续追问。
- Trace 中记录 node_trace、observations、tool_calls、retrieval trace、rerank 状态，方便面试展示排查能力。

## 9. Agent 工作流

当前默认工作流：

```text
User Question
  ↓
load_context        从 SQLite 读取 summary 和最近历史
  ↓
check_permission    根据登录会话角色计算可访问知识库
  ↓
understand_query    LLM / 规则理解问题，输出 route、standalone_query、selected_tool
  ↓
Conditional Edge
  ├─ rag  -> plan_retrieval -> retrieve(search_knowledge_base)
  ├─ tool -> call_tool(get_current_datetime / query_attendance_summary / manage_company_calendar)
  ├─ direct -> generate_answer
  └─ reject -> generate_answer
  ↓
reflect_evidence    RAG 路径判断证据是否足够，不足时补充检索
  ↓
generate_answer     基于证据或工具结果生成最终答案
  ↓
update_memory       写入 SQLite 上下文
```

注意：RAG 本身仍然按 `search_knowledge_base` 工具动作记录在 trace 中，但实际执行位于 `retrieve` 节点；日常业务工具由 `call_tool` 节点通过 registry 执行。

## 10. 检索对比

默认 `RETRIEVAL_MODE=hybrid`：

```text
问题
  ↓
Chroma 向量召回 candidate_k
  ↓
BM25 关键词召回 candidate_k
  ↓
RRF 融合去重
  ↓
Qwen qwen3-rerank 重排 top_n
  ↓
返回 top_k 证据给 Agent / RAG Chain
```

如果要观察纯向量效果：

```bash
mini-rag ask "智能客服平台包含哪些核心模块" --retrieval-mode vector --no-rerank
```

## 11. 目录结构

```text
mini-enterprise-rag-agent/
├── data/raw/                  # 原始文档
├── logs/traces/               # 每次问答的 trace 日志
├── storage/chroma/            # Chroma 向量库持久化目录
├── storage/context.sqlite3    # SQLite 会话上下文
├── storage/langgraph_checkpoints.sqlite3 # LangGraph checkpoint
├── scripts/                   # 常用脚本
├── src/mini_rag/
│   ├── agent/                 # Agent 和工具
│   ├── api/                   # FastAPI 接口
│   ├── ingestion/             # 文档加载、切分、索引构建
│   ├── models/                # Qwen 模型构造
│   ├── observability/         # trace 与计时器
│   ├── rag/                   # 普通 RAG Chain
│   ├── retrieval/             # Chroma 检索
│   ├── config.py              # 配置
│   ├── schemas.py             # API 数据结构
│   └── utils.py               # 通用工具函数
└── README.md
```

## 12. 学习重点

你可以按以下顺序读代码：

1. `src/mini_rag/config.py`：理解环境变量和配置。
2. `src/mini_rag/ingestion/loaders.py`：理解 LangChain 文档加载。
3. `src/mini_rag/ingestion/splitters.py`：理解 Markdown 标题切分和 chunk 切分。
4. `src/mini_rag/ingestion/build_index.py`：理解离线索引构建。
5. `src/mini_rag/retrieval/retriever.py`：理解 Chroma 检索。
6. `src/mini_rag/agent/context_store.py`：理解 SQLite 上下文持久化。
7. `src/mini_rag/agent/context_manager.py`：理解 LLM 如何管理 summary、相关历史和 standalone query。
8. `src/mini_rag/agent/router.py`：理解 LLM Router 和规则兜底。
9. `src/mini_rag/agent/retrieval_planner.py`：理解多模块问题如何拆成多个检索 query。
10. `src/mini_rag/agent/evidence_reflector.py`：理解每轮检索后如何判断证据是否足够。
11. `src/mini_rag/prompts/agent.py`：集中检查各阶段提示词。
12. `src/mini_rag/agent/graph_agent.py`：理解 LangGraph 状态机 Agent。
13. `src/mini_rag/observability/trace.py`：理解如何记录延迟和证据。

## 13. 适合面试时怎么讲

你可以这样介绍项目：

> 我做了一个企业知识库 RAG Agent。离线阶段使用 LangChain DirectoryLoader 接入 Markdown、TXT、PDF、Word，通过 manifest 做增量索引。在线阶段使用向量召回 + BM25 + RRF 融合，再用 Qwen qwen3-rerank 重排证据。Agent 层从脚本式 create_agent 升级为 LangGraph 状态机，包含 load_context、LLM context manager、LLM router、execute_tool、reflect、final、persist_context 等节点。Router 由 LLM 判断是否需要检索；需要检索时，Retrieval Planner 会把多模块问题拆成多个子查询；每轮检索后 Evidence Reflector 再判断证据是否足够，必要时继续补检索。RAG 不重复写成节点，而是作为 search_knowledge_base 工具由 execute_tool 节点调用。上下文持久化到 SQLite，同一 session_id 服务重启后仍能追问。Trace 记录 node_trace、tool_calls、observations、retrieval、证据评估和 rerank 状态，方便排查和面试展示。

## 14. 当前限制

当前版本故意保持小而清晰：

- 暂不支持 PPTX 企业文档解析。
- 考勤和日程工具使用本地 CSV / JSON，适合教学和面试讲解，不是生产级数据库方案。
- 用户、角色和权限是本地演示级实现，生产环境应接入企业 IAM。

这些都可以作为 v0.2 扩展方向。

---

## 企业级 LangGraph Agent 优化版

本版本新增了“企业内部日常使用 Agent”的简化能力：

- 多知识库：`public / hr / finance / it / product`
- 知识库级权限：不同 role 只能检索授权知识库
- 检索前权限过滤：无权限文档不会进入模型上下文
- LangGraph 主流程：`load_context -> check_permission -> understand_query -> route -> rag/tool -> generate_answer -> update_memory`
- 企业日常工具：当前时间、考勤 CSV 汇总、公司日程 JSON 查询/管理
- Audit 日志：`logs/audit.jsonl`
- 前端页面：启动服务后访问 `http://127.0.0.1:8000/`

### 多知识库请求示例

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -d '{
    "user_id": "u001",
    "role": "finance",
    "query": "差旅报销需要哪些材料？",
    "kb_ids": ["finance"],
    "session_id": "demo"
  }'
```

### 权限拦截示例

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -d '{
    "user_id": "u002",
    "role": "employee",
    "query": "差旅住宿标准是多少？",
    "kb_ids": ["finance"]
  }'
```

### 企业日常工具示例

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -d '{
    "user_id": "u003",
    "role": "employee",
    "query": "上周公司的出勤情况怎么样？"
  }'
```

### Admin 接口

```bash
curl http://127.0.0.1:8000/admin/kbs \
  -H "X-API-Key: dev-api-key" \
  -H "X-User-Role: admin"

curl http://127.0.0.1:8000/admin/tools \
  -H "X-API-Key: dev-api-key" \
  -H "X-User-Role: admin"

curl http://127.0.0.1:8000/admin/audit \
  -H "X-API-Key: dev-api-key" \
  -H "X-User-Role: admin"
```

更多说明见 `ENTERPRISE_LANGGRAPH_OPTIMIZATION.md`。
