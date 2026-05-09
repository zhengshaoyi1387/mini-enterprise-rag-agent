# Security：P0 安全设计说明

## 1. 安全目标

本项目的安全目标不是实现完整企业 IAM，而是为 Agent Infra 面试项目建立清晰、可审计、可测试的安全边界：

1. 未授权客户端不能调用核心 Agent 接口。
2. 不同角色只能访问自己被允许的接口。
3. 模型不能绕过程序侧权限直接执行工具。
4. 明显涉及密钥、系统提示词、token 的请求会被拒绝。
5. trace 中可能包含用户问题和内部证据，因此只能 admin 查询。

## 2. API Key 鉴权

核心接口使用 Header：

```text
X-API-Key: dev-api-key
```

对应环境变量：

```text
AGENT_API_KEY=dev-api-key
```

开发环境保留默认值便于本地测试；生产或公开演示时必须改成环境变量注入，不能写死在代码中。

## 3. 角色模型

当前最小角色模型：

| 角色 | 权限说明 |
|---|---|
| guest / public | public 知识库检索、当前日期时间查询 |
| user / employee | 授权知识库检索、当前日期时间、考勤统计、公司日程查询 |
| finance / hr / it | 部门授权知识库检索、当前日期时间、考勤统计、公司日程查询 |
| admin | 全部知识库、trace 查询、用户/角色管理、公司日程写入 |

未知角色会降级为 `guest`。

## 4. Endpoint 权限

```python
ENDPOINT_PERMISSIONS = {
    "health": ["guest", "public", "user", "employee", "finance", "hr", "it", "admin"],
    "query": ["guest", "public", "user", "employee", "finance", "hr", "it", "admin"],
    "chat": ["guest", "public", "user", "employee", "finance", "hr", "it", "admin"],
    "trace": ["admin"],
    "eval": ["admin"],
    "upload": ["user", "employee", "finance", "hr", "it", "admin"],
    "admin_kbs": ["admin"],
    "admin_tools": ["admin"],
    "admin_audit": ["admin"],
}
```

## 5. Tool 权限

```python
TOOL_PERMISSIONS = {
    "search_knowledge_base": ["guest", "public", "user", "employee", "finance", "hr", "it", "admin"],
    "get_current_datetime": ["guest", "public", "user", "employee", "finance", "hr", "it", "admin"],
    "query_attendance_summary": ["user", "employee", "finance", "hr", "it", "admin"],
    "manage_company_calendar": ["user", "employee", "finance", "hr", "it", "admin"],
}
```

新执行链优先使用 action 级权限：

```python
TOOL_ACTION_PERMISSIONS = {
    "search_knowledge_base": {"*": {"guest", "public", "user", "employee", "finance", "hr", "it", "admin"}},
    "get_current_datetime": {"*": {"guest", "public", "user", "employee", "finance", "hr", "it", "admin"}},
    "query_attendance_summary": {"*": {"user", "employee", "finance", "hr", "it", "admin"}},
    "manage_company_calendar": {
        "query": {"user", "employee", "finance", "hr", "it", "admin"},
        "create": {"admin"},
        "update": {"admin"},
        "delete": {"admin"},
    },
}
```

Planner 看到的是按当前 role 和 role policy 过滤后的能力目录；Executor 仍然用 `assert_tool_action_permission()` 做最终权限校验。普通成员看不到 `manage_company_calendar.create/update/delete`，public/guest 看不到公司日程工具本身。管理员配置角色策略时既可以保存工具名，也可以保存 `tool.action` 形式的细粒度策略，例如 `manage_company_calendar.query`。

## 6. 面试回答模板

如果面试官问“你怎么防止模型误调用危险工具？”，可以回答：

> 我不会只依赖 prompt。我的系统有三道边界：API Gateway 做 endpoint 级校验，Planner 只能看到当前角色允许的工具/action，Tool Executor 在执行前再次做 `assert_tool_action_permission`。比如 public 只能看到 search_knowledge_base 和 get_current_datetime；普通成员可以看到日程 query，但看不到 create/update/delete；admin 才能写日程。所有拦截都会进入 trace / audit events。

## 7. 不提交真实密钥

仓库只保留 `.env.example`，真实 `.env` 被 `.gitignore` 忽略。不要提交：

- `.env`
- `storage/`
- `logs/`
- `eval/runs/`
- `__pycache__/`
