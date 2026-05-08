# Architecture：Mini Enterprise RAG Agent P0 架构说明

## 1. 项目定位

本项目定位为一个面向实习/校招面试展示的 **Agentic RAG Infra Mini System**。它不是只把文档塞进向量库后调用一次 LLM，而是把企业知识库问答拆成可治理的工程链路：API Gateway、身份鉴权、权限控制、LangGraph 编排、混合检索、证据反思、trace 可观测和结构化响应。

## 2. 总体架构

```text
Client / curl / Postman
        |
        v
FastAPI Gateway
  - GET  /health
  - POST /chat
  - POST /query   legacy compatibility
  - GET  /traces/{trace_id}
        |
        v
Auth & Permission Layer
  - X-API-Key
  - user_id
  - role: guest/user/employee/finance/hr/it/admin
  - endpoint permission
  - tool permission
        |
        v
LangGraph Agentic RAG Workflow
  - load_context
  - understand_query
  - route
  - plan_retrieval
  - retrieve
  - reflect_evidence
  - generate_answer
  - update_memory
        |
        +-------------------+
        |                   |
        v                   v
Retrieval System        Observability
  - Chroma vector       - trace_id
  - BM25                - node_trace
  - RRF                 - tool_events
  - Qwen rerank         - retrieval_trace
  - cache               - latency_ms
```

## 3. 请求生命周期

1. 客户端调用 `/chat`，Header 携带 `X-API-Key`。
2. FastAPI 用 Pydantic 校验 `ChatRequest`。
3. API Gateway 生成 `trace_id`。
4. 根据 `role` 做 endpoint 级权限检查。
5. 对明显危险请求做轻量安全拒答。
6. 调用复用的 `EnterpriseKnowledgeAgent` 单例，避免每个请求重复初始化重资源。
7. LangGraph 将问题拆成上下文加载、LLM tool planning、路由、检索规划、检索/工具执行、证据反思、回答生成等节点。
8. `understand_query` 由 LLM 输出严格 JSON：`route`、`selected_tool`、`tool_input`、`needs_time_resolution`、`relative_time` 等；关键词规则只提供 `candidate_tool` hint。
9. `retrieve` 节点在真正访问知识库前做 tool permission 检查；日常工具节点可读取本地 CSV / JSON。
10. Agent 产出答案、来源、工具调用、节点耗时和完整 trace。
11. API 保存 trace JSON，并返回结构化 `ChatResponse`。

## 4. 为什么保留 `/query`

`/query` 是旧版教学接口，保留它可以兼容已有脚本和 README 示例。新的面试展示建议统一使用 `/chat`，因为它包含 `user_id`、`role`、`trace_id`、权限控制和更适合工程系统的响应结构。

## 5. 为什么 Agent 要权限层

Agent 能调用工具，而工具可能访问知识库、考勤 CSV 或公司日程 JSON。模型提示词只能降低误调用概率，不能成为安全边界。因此本项目做了两层权限：

- API Gateway：控制谁能访问 `/chat`、`/traces/{trace_id}` 等接口。
- Tool Layer：在工具真正执行前检查当前角色是否允许调用该工具。

这使得即使模型被 prompt injection 诱导，程序侧仍会阻断越权工具调用。

当前工具层只保留 4 个有清晰边界的工具：

- `search_knowledge_base`：非结构化知识库检索，由 `retrieve` 节点执行。
- `get_current_datetime`：解析当前时间和常用相对日期范围。
- `query_attendance_summary`：读取 `data/business/attendance.csv` 做考勤汇总。
- `manage_company_calendar`：读取/写入 `data/business/company_calendar.json`，普通成员只读，admin 可写。

## 6. Tool Planning 与多轮追问

日常工具路线不是关键词规则直调。当前链路是：

```text
load_context
  -> 读取 history 和 previous_tool_context
understand_query
  -> LLM 输出 tool_plan JSON
route
  -> 只做合法性、安全和 trace 记录，不覆盖 LLM selected_tool
call_tool
  -> 程序侧 RBAC、相对时间解析、参数校验、工具执行
generate_answer
  -> LLM 根据 tool_result 生成自然语言回答
update_memory
  -> current_tool_context 写入 trace，下一轮作为 previous_tool_context
```

`select_daily_tool_by_rule` 只产生 `candidate_tool`，用于给 LLM 一个候选提示；正常情况下不会跳过 LLM，也不会在 route 阶段覆盖 LLM 的 `selected_tool`。

工具计划 JSON 的核心字段：

```json
{
  "intent": "rag_fact | daily_tool | direct | reject",
  "route": "rag | tool | direct | reject",
  "standalone_query": "改写后的独立问题",
  "selected_tool": "get_current_datetime | query_attendance_summary | manage_company_calendar | null",
  "required_tools": [],
  "tool_input": {},
  "needs_time_resolution": false,
  "relative_time": null,
  "missing_required_slots": [],
  "reason": "简短说明"
}
```

例如用户先问“昨天公司的出勤情况如何？”，本轮 trace 会保存：

```json
{
  "domain": "attendance",
  "tool_name": "query_attendance_summary",
  "tool_input": {
    "start_date": "2026-05-07",
    "end_date": "2026-05-07",
    "department": "all"
  },
  "result_summary": "2026-05-07 至 2026-05-07 的考勤汇总..."
}
```

下一轮用户问“谁迟到了？”时，`previous_tool_context` 会作为 prompt 输入，LLM 负责补全 `start_date/end_date/status_filter/include_records`，代码只负责校验和执行，不做复杂参数继承。

## 7. 为什么要 trace_id

`trace_id` 是一次请求的唯一标识。它把 API 请求、Agent 节点、检索任务、工具调用、证据反思和最终回答串起来。线上排障时可以定位：

- 路由是否选错；
- tool_plan 是否缺参或选错工具；
- 检索是否召回错误；
- rerank 是否失败或过慢；
- 证据是否不足；
- 生成阶段是否没有遵循引用约束。

## 8. P0 已完成内容

- 新增 `/chat` 工程化接口。
- 新增 `ChatRequest` / `ChatResponse`。
- 新增 `AGENT_API_KEY` 与 `X-API-Key` 校验。
- 新增 `user_id` / `role` 请求级元数据。
- 新增 endpoint permission 与 tool permission。
- `retrieve` 节点执行前做工具权限检查。
- 新增本地 CSV 考勤统计工具和 JSON 公司日程工具。
- 新增 LLM tool planning、`previous_tool_context` 多轮追问参考和相对时间程序侧补全。
- 新增 `/traces/{trace_id}` 可读 trace 查询接口。
- Agent/RAG 对象改为进程级懒加载单例，避免每个请求重复初始化。
- 新增 P0 安全、API、trace 单元测试。
