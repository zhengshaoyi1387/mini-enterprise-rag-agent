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
LangGraph 状态机 Agent：load_context -> plan_intent(execution_plan) -> rag/tool 分支 -> completion_reflect -> generate_answer
  ↓
LLM 检索规划：单问题单 query，多模块问题拆成多个子 query
  ↓
LLM 完成度反思：判断所有子任务是否完成，缺失时补任务后再回答
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
- **Permission-aware Multi-task Planning**：系统先按当前角色生成可用能力目录，Planner 只能看到被授权的工具和 action，再输出 `execution_plan.tasks[]`；简单问题 1 个 task，复合问题多个 task。
- **LLM 上下文管理**：由 Qwen 维护会话摘要、选择相关历史、生成独立检索问题。
- **LLM 检索规划**：需要检索时由 Qwen 判断是否拆成多个子查询，分别召回证据。
- **LLM 完成度反思**：最终回答前由 Qwen 判断原始请求的全部子目标是否完成；未完成时补充 RAG/tool task，再统一生成答案。
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

工具调用不是简单关键词直调，而是：

```text
用户问题
  -> load_context 读取 history 和 previous_tool_context
  -> ToolRegistry 按当前 role 生成 permission-aware available_tool_contracts
  -> plan_intent 由 LLM 输出 execution_plan JSON
  -> 代码做 Planner contract 归一化，修正 route/tool/action 字段冲突
  -> 按当前 task 进入显式 RAG 分支或 tool 分支执行
  -> 代码校验 action 权限、参数和相对时间；必要时内部调用 get_current_datetime
  -> completion_reflect 判断所有子目标是否完成，不完整则补 task
  -> generate_answer 由 LLM 综合 task_results / evidence / tool_result 生成最终答案
  -> current_tool_context 写入 trace，供下一轮追问参考
```

典型多轮例子：

1. 用户：“昨天公司的出勤情况如何？”
   流程：LLM execution_plan -> 内部解析 `yesterday` -> `query_attendance_summary(start_date/end_date)` -> completion_reflect -> LLM 答案
2. 用户：“谁迟到了？”
   流程：`previous_tool_context` 提供上一轮业务上下文 -> LLM 输出完整 task -> `query_attendance_summary(status_filter=late, include_records=true)`
3. 用户：“下周公司有哪些安排？”
   流程：LLM execution_plan -> 内部解析 `next_week` -> `manage_company_calendar(action=query)`
4. 普通用户：“帮我添加明天下午三点的全员会”
   流程：LLM execution_plan -> 内部解析 `tomorrow` -> `manage_company_calendar(action=create)` -> 权限拒绝
5. admin：“帮我添加明天下午三点的全员会”
   流程：LLM execution_plan -> 内部解析 `tomorrow` -> `manage_company_calendar(action=create)` -> 写入 JSON 成功

Planner 输出的核心 schema：

```json
{
  "message_type": "smalltalk | business_question | followup_question | command | unsafe",
  "context_usage": "none | use_history | use_previous_tool_context",
  "intent": "smalltalk | rag_fact | daily_tool | permission_required | direct | reject",
  "route": "direct | rag | tool | reject",
  "selected_tool": "string | null",
  "selected_action": "string | null",
  "tool_input": {},
  "time_requirement": {},
  "execution_plan": {
    "tasks": [
      {
        "task_id": "t1",
        "kind": "rag | tool | direct",
        "objective": "子目标",
        "query": "rag query",
        "tool": "tool name",
        "action": "tool action",
        "tool_input": {},
        "time_requirement": {},
        "depends_on": []
      }
    ]
  }
}
```

`public/guest` 只会在 Planner 能力目录中看到 `search_knowledge_base` 和 `get_current_datetime`；员工能看到 `query_attendance_summary` 和 `manage_company_calendar.query`；只有 admin 能看到 `manage_company_calendar.create/update/delete`。因此普通用户请求写日程时，Planner 应直接输出 `permission_required`，而不是先选择工具再由执行器报错。

程序侧不会盲信 Planner 的单个字段。若 Planner 输出了合法 `selected_tool/selected_action`，但误把 `route` 写成 `direct`，状态机会按结构化 contract 归一化为 `route=tool` 后再执行；若是 `smalltalk`、`permission_required` 或 `reject`，则清空工具字段，避免历史上下文污染当前消息。

日期处理由 Planner 输出结构化 `time_requirement`，执行层只信任该 schema，不在代码里维护关键词路由。凡是相对时间，业务工具执行前都会内部调用 `get_current_datetime`，并用工具结果覆盖模型或上一轮上下文里的日期。`previous_tool_context` 只帮助理解业务对象，例如“下周呢？”延续上一轮日程主题，但“下周”的具体日期永远由当前时间工具给出。

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
AGENT_COMPLETION_MAX_REPLANS=2
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
- 最终回答前由完成度反思阶段判断所有子任务是否完成。
- 最终回答只能基于工具返回、检索证据和完成度反思。
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

- LangGraph 状态机 Agent：显式拆分 load_context、capability catalog、plan_intent、RAG 分支、tool 分支、completion_reflect、generate_answer、update_memory。
- LLM Multi-task Planner：模型基于当前角色可见的能力目录输出 execution_plan，可同时包含 RAG 和 tool 子任务。
- LLM Context Manager：模型维护 summary、选择相关历史、生成 standalone query。
- LLM Retrieval Planner：模型决定是否把一个问题拆成多个检索 query。
- LLM Completion Reflector：最终回答前判断所有子目标是否完成，不足时补充 RAG/tool task。
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
plan_intent         LLM 理解问题，结合 permission-aware contracts 与 previous_tool_context 输出 execution_plan
  ↓
Conditional Edge
  ├─ rag -> plan_retrieval -> retrieve
  ├─ tool -> call_tool
  ├─ direct -> generate_answer
  └─ reject -> generate_answer
  ↓
completion_reflect  判断原始请求所有子任务是否完成，不足时补 task
  ↓
generate_answer     LLM 基于 task_results、证据和工具结果生成最终自然语言答案
  ↓
update_memory       写入 SQLite 上下文
```

注意：RAG 本身仍然按 `search_knowledge_base` 工具动作记录在 trace 中，并由显式 `plan_retrieval -> retrieve` 分支执行；日常业务工具由显式 `call_tool` 分支通过 registry 执行。`completion_reflect` 负责判断是否还有计划任务或补救任务，并把下一步分发回 RAG/tool 分支。`select_daily_tool_by_rule` 已降级为兼容空壳，不参与主路由。

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
7. `src/mini_rag/graph/prompts.py`：理解 LLM execution_plan、检索规划、完成度反思和答案生成提示词。
8. `src/mini_rag/graph/nodes.py`：理解 LangGraph 节点、任务队列、程序侧权限校验、相对时间解析和工具执行。
9. `src/mini_rag/tools/daily_tools.py`：理解真实 daily tools contract 和 event_type 字段语义。
10. `src/mini_rag/tools/attendance_tool.py`：理解 CSV 考勤统计和明细过滤。
11. `src/mini_rag/tools/calendar_tool.py`：理解 JSON 公司日程查询和 admin 写权限。
12. `src/mini_rag/security/permissions.py`：理解 endpoint/tool 权限边界。
13. `src/mini_rag/agent/context_store.py`：理解 SQLite 多轮上下文和 trace 持久化。

## 13. 适合面试时怎么讲

你可以这样介绍项目：

> 我做了一个企业知识库 RAG Agent。离线阶段使用 LangChain DirectoryLoader 接入 Markdown、TXT、PDF、Word，通过 manifest 做增量索引。在线阶段使用向量召回 + BM25 + RRF 融合，再用 Qwen qwen3-rerank 重排证据。Agent 层从脚本式 create_agent 升级为 LangGraph 状态机，包含 load_context、permission-aware tool catalog、plan_intent、显式 RAG/tool 分支、completion_reflect、generate_answer、update_memory 等节点。工具路线不是关键词直调，而是由当前角色可见能力目录约束 LLM 输出严格 JSON execution_plan，代码层做 action-level RBAC、Schema 校验和相对时间补全；复杂问题会拆成多个 RAG/tool task，由 completion_reflect 把下一项任务分发回对应分支，最终回答前再判断子任务是否全部完成。Trace 记录 node_trace、tool_calls、task_results、retrieval、current_tool_context 和完成度评估，方便排查和面试展示。

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
- LangGraph 主流程：`load_context -> check_permission -> capability catalog -> plan_intent(execution_plan) -> rag/tool 分支 -> completion_reflect -> generate_answer -> update_memory`
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
