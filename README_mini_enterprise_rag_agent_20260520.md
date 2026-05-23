# Mini Enterprise RAG Agent

一个面向企业内部知识问答、结构化工具调用和可观测 Agent 工作流的 **Agentic RAG** 项目。

项目从课程式 RAG Demo 重构为更工程化的企业级 Agent 示例：它不只是把文档检索结果塞进 Prompt，而是把用户请求放入一条可追踪、可校验、可评测的 Agent 主链路中，支持权限控制、RAG 证据判断、工具调用、时间解析、流式输出、Trace 日志和离线评测。

---

## 1. 项目定位

这个项目模拟一个企业内部 AI Assistant，用户可以用自然语言完成三类任务：

1. **企业知识库问答**
   - 查询公司制度、报销规则、考勤制度、IT 规范、产品文档等。
   - 支持按角色访问不同知识库，避免越权检索。

2. **结构化工具调用**
   - 查询当前日期时间。
   - 查询公司日程。
   - 创建、修改日程。
   - 查询考勤异常与考勤汇总。

3. **混合任务处理**
   - 同一个问题里既有 RAG 检索，也有工具调用。
   - 例如：先查后天日程，再结合差旅报销制度说明注意事项。

项目目标不是做一个“能聊天”的 Demo，而是展示一个企业 Agent 在真实工程中应该具备的能力：

- 有明确主链路，而不是一堆临时分支。
- 有权限、校验、审计和安全边界。
- 有证据判断，避免 RAG 幻觉。
- 有可观测日志，能定位每一步慢在哪里、错在哪里。
- 有评测集和回归测试，能解释优化是否有效。

---

## 2. 核心亮点

### 2.1 单一 Agentic RAG 主链路

项目当前只保留一条主链路：

```text
/chat 或 /chat/stream
-> EnterpriseKnowledgeAgent
-> EnterpriseKnowledgeGraphAgent
-> AgenticRAGWorkflow
-> build_runtime_context
-> plan_with_llm
-> resolve_plan_time
-> validate_plan
-> react_execute
-> answer_with_llm
-> update_memory
```

相比普通 RAG，这条链路把“理解问题、规划任务、解析时间、校验计划、执行工具或检索、生成回答、更新记忆”拆成明确节点，便于调试、评测和面试讲解。

### 2.2 RAG Evidence Judge

普通 RAG 常见问题是：只要检索到相似文本，就让模型强行回答，容易把“相关内容”当作“充分证据”。

本项目在 RAG 检索后增加了 **Evidence Judge**：

```text
retrieve candidates
-> LLM Evidence Judge 判断候选证据是否足够回答当前子任务
-> sufficient: supporting_sources 进入最终回答
-> insufficient: 触发 Reflect 生成补检索 query
-> retry retrieve
-> 再次 Judge
```

只有 Judge 认可的 `supporting_sources` 才能进入最终回答；`candidate_sources` 只用于 trace/debug，不允许直接引用。

### 2.3 Related Evidence 机制

当知识库没有完整明确依据，但检索到相关内容时，系统不会胡编，也不会简单拒答，而是区分：

- `supporting_sources`：能完整支撑答案的证据。
- `related_sources`：相关但不足以完整回答的问题背景。
- `candidate_sources`：原始候选，只用于调试。

典型回答方式：

```text
当前可访问知识库未找到完整明确依据，因此不能直接确认该结论。
但检索到以下相关内容，可以作为参考：...
```

这可以避免两种极端：

- 没证据也硬答。
- 有相关信息却完全不展示。

### 2.4 Mixed Partial Answerability

多子任务场景中，一个子任务证据不足不应该导致整个问题拒答。

本项目把 answerability 从“全局一票否决”改成“按子任务聚合”：

```text
全部 supported       -> full answer
部分 supported       -> partial answer
全部 unsupported     -> no evidence answer
unsupported + related -> related evidence answer
```

例如用户问：

```text
考勤制度编号是什么？出差酒店费能报销吗？如果可以报销流程是什么？
```

系统可以回答考勤制度编号，同时说明酒店费报销在当前知识库中没有完整明确依据，但可提供差旅报销相关参考。

### 2.5 时间解析与工具安全边界

项目中把相对时间解析独立为 `resolve_plan_time` 节点，避免 Planner 或 Answer LLM 自己乱算日期。

设计原则：

- Planner 保留用户原始时间表达，例如“明天”“后天”“上周”。
- TimeResolver 统一解析成绝对日期或日期范围。
- 工具只消费明确日期，不消费 symbolic date。
- Answer LLM 只能使用工具返回的日期、星期和时间事实。

日程写操作也有安全校验：

- 不允许 `event_id=all`、`multiple`、`*` 之类伪造批量 ID 进入真实工具。
- 修改/删除日程必须有明确事件 ID 或明确选择器。
- 多候选场景默认澄清，不盲目执行。

### 2.6 权限感知

项目模拟企业内部多角色权限：

| 角色 | 默认可访问知识库 | 工具权限示例 |
|---|---|---|
| guest/public | public | 基础问答、当前时间 |
| employee/user | public/hr/it/product | RAG、日程查询、考勤查询 |
| finance | public/finance | 财务知识库、基础工具 |
| hr | public/hr | 人事知识库、考勤查询 |
| it | public/it | IT 知识库、基础工具 |
| admin | public/hr/finance/it/product | 管理接口、日程写操作、角色策略管理 |

权限控制不仅发生在 API 层，也会影响：

- 可见知识库。
- 可见工具。
- 可调用工具 action。
- 最终回答中的权限提示。

### 2.7 可观测 Trace 与 mainline_log

系统同时保留两层日志：

1. **mainline_log**：适合前端展示和面试讲解。
2. **debug trace**：适合开发者定位问题。

每次请求的主线阶段包括：

```text
1. 构建运行上下文
2. 生成执行计划
3. 解析时间信息
4. 校验执行计划
5. 执行任务
6. 生成最终回答
7. 更新记忆
```

debug trace 会记录：

- trace_id
- node_trace
- tool_calls
- llm_calls
- retrieved docs
- supporting / related / candidate sources
- latency summary
- audit events

### 2.8 性能优化

项目针对 Agentic RAG 链路的主要慢点做了优化：

1. **简单任务跳过 next_action LLM**
   - validated 的 tool/rag task 可以 deterministic 执行。
   - 避免 ReAct Executor 重复询问 LLM“下一步该做什么”。

2. **独立 RAG 子任务并发执行**
   - 多个无依赖 RAG 任务可并发检索与 Judge。
   - 工具写操作仍保持串行，避免副作用风险。

3. **模型分层配置**
   - Planner / Judge / Reflect / Answer 可配置不同模型。
   - Judge 和 Reflect 可使用更快模型，Answer 保持高质量模型。

4. **细粒度 latency trace**
   - 分别记录 retrieve、judge、reflect、answer 等阶段耗时。
   - 能定位慢点是在检索、模型判断还是最终回答。

---

## 3. 系统架构

```text
┌─────────────────────┐
│ Web UI / CLI / API   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ FastAPI Gateway      │
│ auth / safety / log   │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────┐
│ EnterpriseKnowledgeAgent      │
│ unified runtime entrance      │
└──────────┬───────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│ AgenticRAGWorkflow                                      │
│                                                         │
│ build_runtime_context                                   │
│ -> plan_with_llm                                        │
│ -> resolve_plan_time                                    │
│ -> validate_plan                                        │
│ -> react_execute                                        │
│ -> answer_with_llm                                      │
│ -> update_memory                                        │
└──────────┬──────────────────────────────────────────────┘
           │
           ├─────────────────────────────┐
           │                             │
           ▼                             ▼
┌─────────────────────┐       ┌──────────────────────────┐
│ Tools               │       │ RAG Retrieval Service     │
│ - datetime           │       │ - hybrid retrieval        │
│ - calendar           │       │ - evidence judge          │
│ - attendance         │       │ - reflect retry           │
└─────────────────────┘       └──────────────────────────┘
           │                             │
           └──────────────┬──────────────┘
                          ▼
              ┌─────────────────────┐
              │ AnswerPacket         │
              │ compact facts only   │
              └──────────┬──────────┘
                          ▼
              ┌─────────────────────┐
              │ Final Answer LLM     │
              └─────────────────────┘
```

---

## 4. 核心链路说明

### 4.1 build_runtime_context

构建请求级运行上下文：

- 用户身份与角色。
- 可访问知识库。
- 可调用工具与 action。
- 当前时间上下文。
- 历史会话摘要。
- previous_tool_context。
- planning_context。

这一层决定“Agent 能看到什么、能用什么”。

### 4.2 plan_with_llm

LLM Planner 负责把用户问题拆成结构化任务。

它只做高层规划，不直接执行，不直接回答，也不负责精确日期计算。

Planner 输出包括：

- overall intent
- 是否需要 RAG
- 是否需要工具
- 子任务列表
- 每个子任务的 kind：`rag` / `tool` / `answer`
- 粗粒度 tool/action
- 用户原始时间表达

### 4.3 resolve_plan_time

把用户的相对时间解析为可执行的绝对时间。

例如：

```text
后天 -> 2026-05-22
上周 -> 2026-05-11 至 2026-05-17
```

这个节点的意义是把“时间计算”从 LLM 自由生成中拿出来，降低星期、日期、范围推断错误。

### 4.4 validate_plan

执行计划进入真实工具前要做校验：

- 权限校验。
- 工具 action 校验。
- schema 校验。
- 日期字段校验。
- 日程写操作安全校验。
- 风险操作 guardrail。

这一层是企业 Agent 的安全边界。

### 4.5 react_execute

当前唯一执行器。

负责执行 validated executable tasks：

- `tool` task 调用结构化工具。
- `rag` task 调用 RAGRetrievalService。
- 简单明确任务跳过 next_action LLM。
- 独立 RAG 任务并发。
- 工具写操作串行。
- 记录 react_steps 和 latency summary。

### 4.6 answer_with_llm

最终回答不直接读取完整 raw trace，而是读取压缩后的 `AnswerPacket`。

AnswerPacket 只包含：

- 用户问题。
- 任务结果摘要。
- resolved time facts。
- 工具结构化结果。
- supporting RAG evidence。
- related evidence。
- safety / permission events。

这样做的目的是：

- 减少 prompt 膨胀。
- 降低模型读错字段的概率。
- 避免 candidate source 误入最终答案。
- 让回答更忠实于工具和证据。

### 4.7 update_memory

更新会话记忆，保留多轮对话需要的摘要和工具上下文。

典型用途：

- 用户先查后天日程，再说“把这个会议改到晚上九点”。
- 系统可以从 previous_tool_context 中找到上一轮候选日程。

---

## 5. RAG 子链路

```text
ReActExecutor.search_rag
-> RAGRetrievalService.retrieve
-> hybrid retrieve
-> LLM Evidence Judge
-> if insufficient: RAG Reflect
-> retry retrieve
-> LLM Evidence Judge
-> selected supporting_sources / related_sources
-> AnswerPacket
-> Final Answer
```

### 5.1 检索

支持：

- Chroma 向量检索。
- BM25 / keyword 风格的 hybrid retrieval。
- metadata 权限过滤。
- source boost。
- 可选 rerank。

### 5.2 Evidence Judge

Judge 只判断“当前子任务”是否有足够证据，不把 original question 中的其他子问题混进来。

输出关键字段：

- answerable
- sufficiency
- supporting_source_ids
- related_source_ids
- missing_evidence
- suggested_retry_query

### 5.3 Reflect Retry

当 Judge 认为证据不足时，系统可以生成一个更贴近当前子任务的 retry query，再检索一次。

Reflect 的作用不是让模型编答案，而是改进检索查询。

### 5.4 Answerability Gate

最终回答阶段会检查每个 RAG task 的证据状态。

- 有 supporting source：可以回答。
- 没有 supporting source 但有 related source：只能作为相关参考。
- 完全没有证据：明确说明当前知识库未找到依据。

---

## 6. 工具能力

### 6.1 get_current_datetime

查询当前日期、时间、星期和常见相对日期范围。

适用问题：

```text
现在几点？
今天是星期几？
上周是哪几天？
```

### 6.2 manage_company_calendar

公司日程工具，支持：

- query：查询日程。
- create：创建日程。
- update：修改日程。
- delete：删除日程。

安全策略：

- 普通用户只能查询。
- admin 才能写操作。
- update/delete 必须有明确 event_id 或明确 selector。
- 不允许伪造批量 event_id。

### 6.3 query_attendance_summary

考勤查询工具，支持按日期范围、部门、员工、状态过滤。

典型问题：

```text
查一下上周有哪些员工存在考勤异常。
产品部本月迟到情况怎么样？
```

---

## 7. 知识库设计

项目内置 5 类企业知识库：

```text
data/kbs/
  public/    # 公共制度、FAQ、办公协作
  hr/        # 考勤、假勤、绩效、招聘、员工关系
  finance/   # 报销、差旅、预算、发票、采购
  it/        # 账号权限、VPN、安全、工单、日志
  product/   # 产品手册、RAG 质量、工具调用、客户方案
```

支持的文档类型包括：

- Markdown
- txt
- docx
- json
- yaml
- csv

每个 chunk 会携带 `kb_id`，检索前按用户角色过滤，避免把无权限文档放入 LLM 上下文。

---

## 8. 项目目录

```text
mini-enterprise-rag-agent/
  data/
    kbs/                         # 企业知识库文档
    business/                    # 日程、考勤等结构化业务数据
    fixtures/                    # 可复现测试数据
  eval/                          # RAG / tool / e2e 评测集
  frontend/                      # 本地 Web UI
  logs/                          # request / audit / trace 日志
  scripts/
    build_index.py               # 构建向量索引
    ask.py                       # 命令行问答
    serve.py                     # 启动服务
    agent_eval_suite.py          # 主评测脚本
    agent_eval_suite_relaxed.py  # 宽松评测脚本
  src/mini_rag/
    agent/                       # EnterpriseKnowledgeAgent 统一入口
    api/                         # FastAPI Gateway、Auth、Admin、Eval API
    graph/                       # AgenticRAGWorkflow、状态定义、Prompt
    orchestration/               # 主节点与 ReActExecutor
    capabilities/                # datetime/calendar/attendance/rag 领域能力
    retrieval/                   # hybrid retrieval、vector store、rerank
    execution/                   # 工具执行与 tool input guardrails
    answer/                      # AnswerPacket、AnswerService、回答策略
    memory/                      # 会话记忆
    observability/               # trace、mainline_log、audit、request log
    security/                    # 用户、角色、权限、安全策略
    tools/                       # 真实工具实现与 registry
  tests/                         # 单元测试、集成测试、架构边界测试
  pyproject.toml
  README.md
```

---

## 9. 快速开始

### 9.1 环境要求

- Python 3.11+
- DashScope / Qwen API Key
- 本地可写目录：`storage/`、`logs/`

### 9.2 安装依赖

```bash
git clone <your-repo-url>
cd mini-enterprise-rag-agent

python -m venv .venv
source .venv/bin/activate

pip install -e .
```

开发环境可额外安装测试依赖：

```bash
pip install -e '.[dev]'
```

### 9.3 配置环境变量

复制 `.env.example`：

```bash
cp .env.example .env
```

至少填写：

```env
DASHSCOPE_API_KEY=your-dashscope-api-key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_CHAT_MODEL=qwen-plus
QWEN_CONTROL_MODEL=qwen-plus
QWEN_EMBEDDING_MODEL=text-embedding-v4
```

推荐的 Agent 模型分层配置：

```env
PLANNER_MODEL=qwen-plus
RAG_JUDGE_MODEL=qwen-turbo
RAG_REFLECT_MODEL=qwen-turbo
ANSWER_MODEL=qwen-max
```

如果想降低成本，可以把 `ANSWER_MODEL` 也换成 `qwen-plus`。

### 9.4 构建知识库索引

```bash
python scripts/build_index.py --reset
```

或使用 CLI：

```bash
mini-rag build-index --reset
```

索引默认写入：

```text
storage/chroma
storage/index_manifest.json
```

### 9.5 启动服务

```bash
uvicorn mini_rag.api.app:app --reload
```

或：

```bash
mini-rag serve --host 127.0.0.1 --port 8000
```

启动后访问：

```text
http://127.0.0.1:8000/
```

### 9.6 默认账号

本地 Demo 默认初始化以下账号：

| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | admin |
| employee | employee123 | employee |
| finance | finance123 | finance |
| hr | hr123 | hr |
| it | it123 | it |
| guest | guest123 | guest |

生产环境请务必修改默认账号和密码。

### 9.7 登录并调用 /chat

登录：

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

拿到 `access_token` 后调用：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "考勤与休假管理制度的文档编号是多少？8000元以上报销要注意什么？",
    "session_id": "demo-session",
    "kb_ids": ["hr", "finance"],
    "retrieval_mode": "hybrid"
  }'
```

### 9.8 流式接口

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "查一下后天的所有日程，再告诉我如果要出差报销需要注意什么",
    "session_id": "demo-stream"
  }'
```

`/chat/stream` 会返回 NDJSON 风格事件：

```json
{"event":"status","stage":"runtime_context","message":"正在理解问题"}
{"event":"status","stage":"plan_with_llm","message":"正在生成执行计划"}
{"event":"token","content":"..."}
{"event":"final","trace_id":"...","answer":"..."}
```

### 9.9 CLI 问答

```bash
mini-rag ask "8000元以上的账单报销时应该注意什么？"

python scripts/ask.py "查一下产品部上周考勤异常，再结合考勤制度说明常见处理方式。"
```

---

## 10. 常用 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/auth/login` | 登录 |
| GET | `/auth/me` | 当前用户信息 |
| POST | `/auth/logout` | 登出 |
| POST | `/chat` | 非流式 Agent 问答 |
| POST | `/chat/stream` | 流式 Agent 问答 |
| GET | `/traces/{trace_id}` | 查看可读 trace，admin 可用 |
| GET | `/admin/kbs` | 查看知识库，admin 可用 |
| POST | `/admin/kbs/{kb_id}/documents` | 导入知识库文档，admin 可用 |
| DELETE | `/admin/kbs/{kb_id}/documents/{document_path}` | 删除知识库文档，admin 可用 |
| POST | `/admin/kbs/reindex` | 重建索引，admin 可用 |
| GET | `/admin/tools` | 查看工具列表，admin 可用 |
| GET | `/admin/audit` | 查看审计日志，admin 可用 |
| GET | `/admin/users` | 查看用户，admin 可用 |
| POST | `/admin/users` | 创建用户，admin 可用 |
| PATCH | `/admin/users/{username}` | 修改用户，admin 可用 |
| GET | `/admin/roles` | 查看角色策略，admin 可用 |
| PATCH | `/admin/roles` | 修改角色策略，admin 可用 |
| POST | `/eval/run` | 兼容评测 API，推荐使用脚本评测 |

---

## 11. 评测与测试

### 11.1 单元测试与集成测试

```bash
PYTHONPATH=src python -m compileall -q src tests
PYTHONPATH=src python -m pytest tests -q
```

测试覆盖内容包括：

- API 鉴权。
- 权限控制。
- RAG answerability gate。
- Hybrid retrieval。
- Time resolver。
- Calendar validator。
- Tool executor。
- AnswerPacket。
- Mainline log。
- Trace store。
- 前端 mainline UI。
- 性能契约。
- 主线清理边界。

### 11.2 评测集

项目内置评测集：

```text
eval/agent_eval_cases_full/
  rag_eval_questions.jsonl
  tool_eval_cases.jsonl
  agent_e2e_eval_cases.jsonl
  all_eval_cases.jsonl
```

当前 full eval manifest 中包含：

```text
RAG cases: 32
Tool cases: 40
E2E cases: 20
Total: 92
```

### 11.3 运行评测

RAG / Tool / E2E 评测统一走 `EnterpriseKnowledgeAgent`，不绕过 Agentic 主线。

```bash
PYTHONPATH=src python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --judge rule \
  --questions eval/agent_eval_cases_full/agent_e2e_eval_cases_aligned.jsonl \
  --output outputs/eval/e2e_report
```

也可以运行完整评测：

```bash
PYTHONPATH=src python scripts/agent_eval_suite_relaxed.py \
  --suite all \
  --judge rule \
  --questions eval/agent_eval_cases_full/all_eval_cases.jsonl \
  --output outputs/eval/full_report
```

---

## 12. 可观测性

### 12.1 mainline_log

前端默认展示轻量执行状态，例如：

```text
正在理解问题...
正在生成执行计划...
正在解析时间信息...
正在校验执行计划...
正在执行任务...
正在组织最终回答...
正在更新记忆...
```

每个阶段会有标题、摘要和必要细节，适合用户理解 Agent 正在做什么。

### 12.2 Debug Trace

完整 trace 默认保存在：

```text
logs/traces/
```

请求日志：

```text
logs/requests.jsonl
```

审计日志：

```text
logs/audit.jsonl
```

### 12.3 LLM IO Trace

`.env` 中可以控制是否记录完整 LLM 输入输出：

```env
TRACE_LLM_IO=true
TRACE_LLM_IO_MAX_CHARS=0
```

- `TRACE_LLM_IO=true`：记录模型调用输入输出，便于调试。
- `TRACE_LLM_IO_MAX_CHARS=0`：不截断。
- 生产环境建议关闭或设置截断，避免日志过大或暴露敏感信息。

---

## 13. 推荐演示问题

### 13.1 单 RAG

```text
8000元以上的账单报销时应该注意什么？
```

预期：

- route: rag
- 命中 finance 知识库
- Evidence Judge 认可 supporting source
- 最终回答带制度依据

### 13.2 多 RAG 并发

```text
考勤与休假管理制度的文档编号是多少？8000元以上报销要注意什么？VPN远程访问有什么安全要求？
```

预期：

- 拆成多个 RAG 子任务
- 分别命中 hr / finance / it
- 独立 RAG 任务并发执行
- 最终合并回答

### 13.3 Related Evidence

```text
考勤与休假管理制度的文档编号是多少？出差的酒店花费可以报销吗？如果可以报销，报销流程是怎么样的？
```

预期：

- 考勤制度编号可以回答
- 酒店费是否可报销若证据不足，不强答
- 提供差旅报销相关参考

### 13.4 日程查询

```text
查一下后天的所有日程
```

预期：

- Planner 保留“后天”
- TimeResolver 解析具体日期
- Calendar 工具返回结构化日程
- Answer 只使用工具返回日期和 weekday

### 13.5 多轮日程修改

第一轮：

```text
查一下后天的所有日程
```

第二轮：

```text
把这个会议改到晚上九点到九点半
```

预期：

- 第二轮使用 previous_tool_context
- 找到上一轮明确会议
- admin 角色可执行 update
- 非 admin 角色被权限拒绝

### 13.6 考勤异常

```text
查一下上周有哪些员工存在考勤异常，给我
```

预期：

- 上周解析为明确日期范围
- status filters 包含 late / leave / absent
- 返回按员工或记录聚合的异常情况

---

## 14. 关键配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `DASHSCOPE_API_KEY` | 无 | Qwen / DashScope API Key |
| `QWEN_BASE_URL` | DashScope compatible mode | OpenAI 兼容接口地址 |
| `QWEN_CHAT_MODEL` | `qwen-max` | 默认聊天模型 |
| `QWEN_CONTROL_MODEL` | `qwen-plus-2025-07-14` | 控制类 JSON 输出模型 |
| `PLANNER_MODEL` | 空 | Planner 独立模型 |
| `RAG_JUDGE_MODEL` | 空 | Evidence Judge 独立模型 |
| `RAG_REFLECT_MODEL` | 空 | RAG Reflect 独立模型 |
| `ANSWER_MODEL` | 空 | 最终回答模型 |
| `QWEN_EMBEDDING_MODEL` | `text-embedding-v4` | embedding 模型 |
| `DATA_DIR` | `data/kbs` | 企业知识库目录 |
| `CHROMA_DIR` | `storage/chroma` | Chroma 持久化目录 |
| `RETRIEVAL_MODE` | `hybrid` | 检索模式 |
| `TOP_K` | `3` | 返回证据数量 |
| `CANDIDATE_K` | `8` | 候选召回数量 |
| `RERANK_ENABLED` | `false` | 是否开启 rerank |
| `RERANK_TOP_N` | `3` | rerank 后保留数量 |
| `AGENT_PARALLEL_RAG_TASKS` | `3` | 并发 RAG 子任务数 |
| `AGENT_REFLECT_MAX_ROUNDS` | `2` | RAG Reflect 最大轮数 |
| `AGENT_MAX_STEPS` | `10` | Agent 最大执行步数 |
| `SESSION_MAX_TURNS` | `6` | 会话记忆保留轮数 |
| `SAVE_TRACE` | `true` | 是否保存 trace |
| `TRACE_LLM_IO` | `true` | 是否记录 LLM 输入输出 |
| `AGENT_FIXED_NOW` | 空 | 固定当前时间，用于评测复现 |

---

## 15. 这个项目和普通 RAG Demo 的区别

| 维度 | 普通 RAG Demo | 本项目 |
|---|---|---|
| 主链路 | 检索 -> 拼 Prompt -> 回答 | Agentic workflow，多节点可观测 |
| 意图处理 | 简单关键词或直接问答 | LLM Planner 结构化规划 |
| 时间处理 | 让 LLM 自己推 | 独立 TimeResolver |
| 工具调用 | 简单 function call | 权限、schema、validator、guardrail |
| RAG 证据 | 相似文本直接进 Prompt | Evidence Judge 过滤 supporting evidence |
| 证据不足 | 容易胡答或直接拒答 | Reflect retry + related evidence |
| 多任务 | 容易混乱 | per-task execution + partial answer |
| 权限 | 通常没有 | KB、工具、action 多层权限 |
| 日志 | 打印结果 | mainline_log + debug trace + audit log |
| 评测 | 手工试 | RAG / Tool / E2E 评测集 |
| 面试展示 | 概念 Demo | 可解释的工程系统 |

---

## 16. 面试讲解版

可以这样介绍项目：

```text
我这个项目是一个企业级 Agentic RAG Demo，目标不是做一个简单知识库问答，而是模拟企业内部 AI Assistant 的完整链路。

它的主链路包括运行上下文构建、LLM 规划、时间解析、计划校验、ReAct 执行、最终回答和记忆更新。用户的问题会先进入 Planner，被拆成 RAG 任务、工具任务或普通回答任务；涉及“明天、后天、上周”这类表达时，不让模型自己算日期，而是交给 TimeResolver 解析成确定日期；执行前再经过权限和 schema 校验，防止越权访问和危险工具调用。

RAG 部分我没有直接把检索结果给模型回答，而是增加了 Evidence Judge。检索出的 candidate sources 必须经过 Judge 判断，只有能完整支撑当前子任务的 supporting sources 才能进入最终回答。如果证据不足，会触发 Reflect 生成补检索 query 再检索一次。如果仍然证据不足，但有相关内容，就以 related evidence 的方式展示，明确告诉用户这些只能作为参考，不能直接支撑结论。

性能方面，我通过 trace 发现慢点主要在多次 LLM 串行调用，所以做了三类优化：第一，validated 的简单任务跳过 ReAct next_action LLM；第二，无依赖的 RAG 子任务并发执行；第三，Planner、Judge、Reflect、Answer 支持独立模型配置，让 Judge/Reflect 可以用更快模型，Answer 保持质量模型。

工程上我还做了权限控制、审计日志、mainline_log、debug trace、RAG/Tool/E2E 评测集，以及一个简单前端用于展示执行过程。这个项目重点展示的是：如何把不确定的大模型能力放进一个可观测、可校验、可评测的企业应用系统里。
```

---

## 17. 已知边界与后续优化

当前项目更偏面试展示和工程 Demo，不是生产级系统。后续可以继续优化：

1. **纯工具查询模板回答**
   - 对 calendar.query / attendance.query 等结构化工具结果，可直接模板化回答，减少 Answer LLM 延迟。

2. **更完善的 RAG 评测**
   - 引入 Recall@k、MRR、NDCG、引用命中率、Judge 准确率等指标。

3. **更细的权限模型**
   - 支持文档级、字段级权限，而不仅是知识库级权限。

4. **工具写操作确认节点**
   - 对 create/update/delete 增加用户确认工作流。

5. **生产级部署**
   - 增加 Dockerfile、CI、异步队列、限流、重试、监控告警。

6. **更强的上下文工程**
   - 对历史会话、工具结果和 RAG 证据做更细粒度压缩和缓存。

---

## 18. 安全说明

本项目包含本地 Demo 默认账号、示例知识库和模拟业务数据，仅用于学习、面试展示和本地实验。

生产环境使用前至少需要：

- 修改默认账号密码。
- 关闭或脱敏完整 LLM IO trace。
- 使用真实鉴权系统替代本地 SQLite demo auth。
- 增加 HTTPS、网关限流和访问审计。
- 对工具写操作增加二次确认。
- 对日志和知识库做敏感信息扫描。

---

## 19. 技术栈

- Python 3.11+
- FastAPI
- LangChain
- LangGraph
- ChromaDB
- Qwen / DashScope OpenAI-compatible API
- Pydantic / pydantic-settings
- SQLite
- Typer / Rich
- pytest
- 原生 HTML/CSS/JavaScript 前端

---

## 20. 项目关键词

```text
Agentic RAG
Enterprise AI Assistant
LangGraph Workflow
ReAct Executor
RAG Evidence Judge
RAG Reflect
Related Evidence
Hybrid Retrieval
Tool Calling
Permission-aware RAG
Context Engineering
AnswerPacket
Trace Observability
Mainline Log
Agent Evaluation
```
