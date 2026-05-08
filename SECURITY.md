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
| guest | 普通知识库检索和问答 |
| user | 知识库检索、总结、对比、读写自己的 memory |
| admin | trace 查询、eval、管理类工具 |

未知角色会降级为 `guest`。

## 4. Endpoint 权限

```python
ENDPOINT_PERMISSIONS = {
    "health": ["guest", "user", "admin"],
    "query": ["guest", "user", "admin"],
    "chat": ["guest", "user", "admin"],
    "trace": ["admin"],
    "eval": ["admin"],
    "upload": ["user", "admin"],
}
```

## 5. Tool 权限

```python
TOOL_PERMISSIONS = {
    "search_knowledge_base": ["guest", "user", "admin"],
    "summarize_sources": ["guest", "user", "admin"],
    "rewrite_query": ["guest", "user", "admin"],
    "generate_study_plan": ["guest", "user", "admin"],
    "compare_sources": ["user", "admin"],
    "read_memory": ["user", "admin"],
    "save_memory": ["user", "admin"],
    "run_eval": ["admin"],
}
```

## 6. 面试回答模板

如果面试官问“你怎么防止模型误调用危险工具？”，可以回答：

> 我不会只依赖 prompt。我的系统有两层权限：API Gateway 做 endpoint 级校验，Tool Layer 在工具真正执行前做程序侧权限检查。即使 LLM 被诱导输出某个工具调用，执行前也会根据 role 和 TOOL_PERMISSIONS 强制拦截，并把拦截结果写入 trace。

## 7. 不提交真实密钥

仓库只保留 `.env.example`，真实 `.env` 被 `.gitignore` 忽略。不要提交：

- `.env`
- `storage/`
- `logs/`
- `eval/runs/`
- `__pycache__/`
