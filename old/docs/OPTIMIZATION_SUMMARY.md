# mini-enterprise-rag-agent 优化说明

本次优化目标：在不牺牲企业 RAG / 工具调用正确性的前提下，提高响应速度并修复 follow-up 规划错误。

## 关键修复

1. Planner contract validation 加强
   - 当 `context_usage=use_previous_tool_context` 且上一轮存在结构化工具上下文时，`validate_plan` 会把不一致的 `direct` 规划纠正为可执行工具计划。
   - 修复 “下下周呢” 被错误 route 到 direct、再调用回答模型生成泛泛解释的问题。

2. 相对时间协议增强
   - `canonical_relative` 支持 `week_after_next` / `month_after_next`。
   - `get_current_datetime` 输出下下周、下下月的确定日期范围。
   - 执行层继续负责相对时间落地，不信任 LLM 猜测的日期。

3. 权限感知能力目录修复
   - 修复 `manage_company_calendar.query` 这类 action-scoped role policy 没有正确收窄 action 的问题。
   - role policy 现在只能在基础 role 权限内收窄，不能越权扩张。

4. 性能优化
   - 在一次 workflow run 内缓存 role policy snapshot，避免多个节点重复读 SQLite。
   - 对工具路径保持“工具结果直接格式化”，避免错误进入 `qwen-plus generate_answer`。
   - trace 仍保留关键节点和观察信息，不恢复膨胀输出。

5. 兼容性修复
   - 增加 pytest `pythonpath = ["src"]`。
   - 保留 `select_daily_tool_by_rule` 的弃用兼容 shim，始终返回 None，不恢复规则/fast path。
   - 修复 Pydantic 校验后 `file_path` 等运行时参数被丢弃导致测试工具文件不可用的问题。
   - 工具 slot 缺失时返回更友好的错误，不泄漏 Pydantic 原始错误。

## 新增测试

新增 `tests/test_planner_contract_validation.py`：

- `test_followup_previous_calendar_context_cannot_stay_direct`
- `test_week_after_next_calendar_query_uses_datetime_tool`

覆盖：

- “下下周呢” 不能再落到 direct。
- 会继承上一轮 calendar 工具上下文。
- 会调用 `get_current_datetime` 解析下下周日期。
- 会继续调用 `manage_company_calendar.query`。

## 本地验证结果

已通过：

```bash
python -m compileall src
```

以下测试文件已逐个执行通过：

```bash
tests/test_daily_tools.py
tests/test_agentic_refactor_pure.py
tests/test_llm_tool_planning.py
tests/test_permissions.py
tests/test_auth_flow.py
tests/test_context_store.py
tests/test_evaluation_metrics.py
tests/test_manifest.py
tests/test_readable_trace.py
tests/test_request_logger.py
tests/test_trace_store.py
tests/test_planner_contract_validation.py
```

`python scripts/serve.py` 使用 5 秒外部 timeout 验证，日志显示 Uvicorn 和应用启动完成后被主动停止。

完整 `pytest -q` 在当前容器中未完成 collection，因为环境缺少 LangChain 相关依赖：`langchain_core`、`langchain_openai`。这不是本次代码改动引入的问题。
