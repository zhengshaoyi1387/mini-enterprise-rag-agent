# 企业级 LangGraph Agent 优化说明

## 目标

本版本把原项目从“单知识库 Agentic RAG Demo”升级为“简化企业内部 Agent”：支持多知识库、知识库级权限、LangGraph 主图编排、办公工具、Trace、Audit 和前端可视化。

## 核心设计

### 1. 知识库级权限，不给 chunk 单独配权限

权限规则集中在 `src/mini_rag/security/permissions.py`：

```python
ROLE_ALLOWED_KBS = {
    "admin": ["public", "hr", "finance", "it", "product"],
    "employee": ["public", "hr", "it", "product"],
    "finance": ["public", "finance"],
    "hr": ["public", "hr"],
    "guest": ["public"],
}
```

chunk 只保存归属 metadata：

```python
metadata["kb_id"] = "finance"
metadata["kb_name"] = "财务知识库"
```

检索时只在 `allowed_kbs` 中查，避免无权限内容进入模型上下文。

### 2. LangGraph 主流程

```text
load_context
  -> check_permission
  -> understand_query
  -> route
      -> rag:  plan_retrieval -> retrieve -> reflect_evidence -> generate_answer
      -> tool: call_tool -> generate_answer
      -> reject/direct: generate_answer
  -> update_memory
```

新增节点：

- `check_permission`：根据 role + requested_kbs 计算 allowed_kbs。
- `call_tool`：统一执行办公工具，执行前做工具权限检查。

### 3. Prompt 重点优化

你之前指出的问题是正确的：`understand_query` 已经生成语义完整的 `standalone_query`，后续 `plan_retrieval` 不应该再改写扩大问题。

本版本在 `PLAN_RETRIEVAL_SYSTEM` 中明确要求：

- 默认原样使用 `standalone_query`。
- 禁止添加用户没要求的“原理、优势、案例、风险、最佳实践”等维度。
- 只有明确多对象比较/解释时才拆成最多 3 个任务。

同时在代码层 `_optimize_search_tasks` 做二次护栏：普通问题强制回到 `standalone_query`，防止 LLM 扩写导致召回变差。

### 4. 办公工具

新增 `src/mini_rag/tools/`：

- `generate_weekly_report`：周报草稿
- `draft_email`：邮件草稿
- `create_it_ticket`：IT 工单草稿
- `check_reimbursement_rule`：报销规则初步判断
- `generate_leave_request`：请假申请草稿

这些工具只生成草稿，不真实提交，适合面试演示低风险 Tool Calling。

### 5. Trace 与 Audit

Trace：

```text
logs/traces/{trace_id}.json
```

用于调试 LangGraph 节点、检索、工具调用和 LLM 调用。

Audit：

```text
logs/audit.jsonl
```

用于记录用户访问知识库、工具调用、权限拦截和安全拒答。

## 新增 API

```text
GET  /
GET  /ui
GET  /admin/kbs
GET  /admin/tools
GET  /admin/audit
POST /chat
GET  /traces/{trace_id}
POST /eval/run
```

## 演示建议

1. 用 `finance` 角色访问 `finance` 知识库，展示成功检索。
2. 用 `employee` 角色访问 `finance`，展示权限拦截。
3. 问“帮我写一份周报”，展示工具调用。
4. 打开 `/admin/audit`，展示审计记录。
5. 打开 `/traces/{trace_id}`，展示 LangGraph 节点 trace。
