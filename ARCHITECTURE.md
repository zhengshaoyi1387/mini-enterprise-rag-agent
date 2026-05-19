# Architecture：Mini Enterprise RAG Agent P0 架构说明

## 1. 项目定位

本项目定位为一个面向实习/校招面试展示的 **Agentic RAG Infra Mini System**。它不是只把文档塞进向量库后调用一次 LLM，而是把企业知识库问答拆成可治理的工程链路：API Gateway、身份鉴权、权限控制、LangGraph 编排、混合检索、最终完成度反思、trace 可观测和结构化响应。

## 2. 总体架构

```text
Client / curl / Postman
        |
        v
FastAPI Gateway
  - GET  /health
  - POST /chat
  - POST /query   compatibility endpoint
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
  - build_capability_catalog
  - build_planning_context
  - plan_intent
  - validate_plan
  - route
  - plan_retrieval / retrieve
  - call_tool
  - completion_reflect
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
7. LangGraph 将问题拆成上下文加载、权限感知能力目录、LLM 多任务规划、显式 RAG/tool 分支执行、完成度反思、回答生成等节点。
8. `plan_intent` 由 LLM 输出严格 JSON：`message_type`、`context_usage`、`route`、`selected_tool`、`selected_action`、`time_requirement`、`execution_plan.tasks[]` 等；关键词规则不参与主流程。
9. `route` 将当前 task 分发到显式分支：RAG task 走 `plan_retrieval -> retrieve`；tool task 走 `call_tool`，并复用本地 CSV / JSON 工具、schema 校验和 action-level RBAC。
10. Agent 产出答案、来源、工具调用、节点耗时和完整 trace。
11. API 保存 trace JSON，并返回结构化 `ChatResponse`。

## 4. 为什么保留 `/query`

`/query` 是轻量兼容接口，保留它可以兼容已有 curl/Postman 示例。新的面试展示建议统一使用 `/chat`，因为它包含 `user_id`、`role`、`trace_id`、权限控制和更适合工程系统的响应结构。

## 5. 为什么 Agent 要权限层

Agent 能调用工具，而工具可能访问知识库、考勤 CSV 或公司日程 JSON。模型提示词只能降低误调用概率，不能成为安全边界。因此本项目做了两层权限：

- API Gateway：控制谁能访问 `/chat`、`/traces/{trace_id}` 等接口。
- Tool Layer：在工具真正执行前检查当前角色是否允许调用该工具及 action。

这使得即使模型被 prompt injection 诱导，程序侧仍会阻断越权工具调用。

当前工具层只保留 4 个有清晰边界的工具：

- `search_knowledge_base`：非结构化知识库检索，由 `retrieve` 节点执行。
- `get_current_datetime`：解析当前时间和常用相对日期范围。
- `query_attendance_summary`：读取 `data/business/attendance.csv` 做考勤汇总。
- `manage_company_calendar`：读取/写入 `data/business/company_calendar.json`，普通成员只读，admin 可写。

## 6. Multi-task Planning、完成度反思与多轮追问

日常工具路线不是关键词规则直调。当前链路是：

```text
load_context
  -> 读取 history 和 previous_tool_context
Permission-aware Capability Catalog
  -> ToolRegistry 根据 role 过滤工具和 action
plan_intent
  -> LLM 只基于 available_tool_contracts 输出 execution_plan JSON
Planner Contract Normalizer
  -> 程序侧修正 route/tool/action 冲突，清理 direct-only 消息里的工具字段
route
  -> 只做合法性、安全和 trace 记录，不覆盖 LLM selected_tool
rag/tool branch
  -> RAG 走 plan_retrieval -> retrieve，tool 走 call_tool，统一写入 task_results
completion_reflect
  -> 判断原始请求的所有子目标是否完成；还有计划任务或缺失目标时分发回 RAG/tool 分支
generate_answer
  -> LLM 根据 task_results、tool_result、证据和 completion_assessment 生成自然语言回答
update_memory
  -> current_tool_context 写入 trace，下一轮作为 previous_tool_context
```

`select_daily_tool_by_rule` 不参与主流程。Planner 能看到的只有 `available_tool_contracts`：`public/guest` 看不到考勤和公司日程；普通员工只能看到 `manage_company_calendar.query`；admin 才能看到 `query/create/update/delete`。

Planner JSON 的核心字段：

```json
{
  "message_type": "smalltalk | business_question | followup_question | command | unsafe",
  "context_usage": "none | use_history | use_previous_tool_context",
  "intent": "smalltalk | rag_fact | daily_tool | permission_required | direct | reject",
  "route": "direct | rag | tool | reject",
  "standalone_query": "改写后的独立问题",
  "selected_tool": "string | null",
  "selected_action": "string | null",
  "required_tools": [],
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
  },
  "missing_required_slots": [],
  "reason": "简短说明"
}
```

Action-level 权限由 `TOOL_ACTION_PERMISSIONS` 描述，Executor 使用 `assert_tool_action_permission()` 做最终拦截。即使 Planner 被诱导输出了越权 action，执行阶段仍会返回业务友好的权限提示，不会把内部工具名暴露给普通用户。

Planner 输出不是单字段可信的。`understand_query` 之后会先进入 contract normalizer：合法且授权的 `selected_tool/selected_action` 与 `route=direct` 冲突时，以可执行工具选择为准归一化成 `route=tool`；`smalltalk`、`permission_required`、`reject` 则清空工具字段。这样多轮追问不会因为 Planner 某个字段写错而跳过工具，也不会把寒暄误导到上一轮工具上下文。

相对日期是另一条程序侧硬边界。Planner 负责输出结构化 `time_requirement`，代码不维护关键词路由。`previous_tool_context` 可以帮助判断“下周呢？”是在追问公司日程还是考勤，但不能提供“下周”的日期。业务工具执行前会内部调用 `get_current_datetime` 并覆盖任何模型猜测或上下文推导出来的 `start_date/end_date`。

`completion_reflect` 是最终回答前的质量闸门。它查看原始问题、`execution_plan`、`task_results`、工具结果和检索证据，输出 `ready_to_answer`、`missing_objectives`、`unsupported_parts` 和 `followup_tasks`。如果发现 Planner 漏掉子目标，例如只查了报销制度但没有查日程，状态机会补执行缺失 task，再进入最终回答。

Smalltalk 不是 fast path。Planner 必须输出 `message_type=smalltalk`、`context_usage=none`、`route=direct`，这样“你好/谢谢/再见”不会被上一轮 `previous_tool_context` 污染，也不会走 RAG 或工具。

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

`trace_id` 是一次请求的唯一标识。它把 API 请求、Agent 节点、检索任务、工具调用、完成度反思和最终回答串起来。线上排障时可以定位：

- 路由是否选错；
- execution_plan 是否漏掉子目标、缺参或选错工具；
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
- 新增 LLM multi-task planning、`previous_tool_context` 多轮追问参考和相对时间程序侧补全。
- 新增显式 RAG/tool 分支与 `completion_reflect`，支持复合问题多任务执行和最终回答前完整性检查。
- 新增 permission-aware capability catalog 和 action-level tool permission。
- 新增 `/traces/{trace_id}` 可读 trace 查询接口。
- Agent/RAG 对象改为进程级懒加载单例，避免每个请求重复初始化。
- 新增 P0 安全、API、trace 单元测试。
