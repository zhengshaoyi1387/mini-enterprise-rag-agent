# Final Architecture Refactor Report

## 1. Summary

本轮按 `CODEX_ONE_SHOT_OPTIMIZATION_PLAN.md` 做架构收口，目标从追逐单个 eval case 满分切换为：时间可复现、职责清晰、执行安全、评测可信、旧入口瘦身、项目清理。

当前确认：

- 单测：`214 passed`
- `compileall src`：通过
- aligned 12：12/12
- V2 first20：20/20
- RAG clean full32：32/32
- V2 full64：最终重跑被 DashScope `AllocationQuota.FreeTierOnly` 在第 1 条阻断，infra 单独统计，不计 Agent failure

## 2. Architecture Changes

- TimeContext：新增 fixed-now 和 request-level cache，同一请求复用 `time_context_result`。
- CapabilityRegistry：从 contract metadata 升级为 contract + handler registry，支持 role-filtered visibility 和统一 `compile/validate/resolve/format_answer`。
- Planning：`graph/planning_contract.py` 变为兼容 facade，主体迁到 `planning/contract_normalizer.py`。
- Graph nodes：`graph/nodes.py` 变为 60 行兼容边界，运行时迁到 `orchestration/agentic_nodes.py`。
- Tool input：`tools/input_contract.py` 变为 shim，主体迁到 `execution/tool_input.py`。
- Eval：两套 eval 脚本增加 `failure_category` 和 `failure_categories` 汇总；eval 默认 fixed now。

## 3. Files Changed

主要新增/迁移：

- `src/mini_rag/orchestration/agentic_nodes.py`
- `src/mini_rag/planning/contract_normalizer.py`
- `src/mini_rag/execution/tool_input.py`
- `tests/test_time_context_fixed_now.py`
- `tests/test_time_context_cache.py`
- `tests/test_capability_registry_integration.py`
- `tests/test_planning_contract_facade.py`
- `tests/test_nodes_orchestration_boundary.py`
- `tests/test_tool_input_ownership.py`

主要修改：

- `src/mini_rag/capabilities/datetime/service.py`
- `src/mini_rag/tools/datetime_tool.py`
- `src/mini_rag/capabilities/registry.py`
- `src/mini_rag/core/contracts.py`
- `src/mini_rag/graph/nodes.py`
- `src/mini_rag/graph/planning_contract.py`
- `src/mini_rag/tools/input_contract.py`
- `scripts/agent_eval_suite.py`
- `scripts/agent_eval_suite_relaxed.py`
- `src/mini_rag/api/schemas.py`
- `src/mini_rag/api/app.py`
- `src/mini_rag/agent/agent.py`
- `src/mini_rag/agent/graph_agent.py`

## 4. Removed / Moved to old2

已移动：

- `old2/pycache_20260518_final_after_verify/`
- `old2/eval_outputs_round10_20260518/`
- `old2/reports_pre_final_20260518/`

保留：

- `outputs/eval/final_*`
- `outputs/final_architecture_refactor_report_20260518.md`

检查结果：源码、脚本、测试中没有指向 `old2/` 的依赖。

## 5. TimeContext / Fixed Now

实现：

- `build_time_context()`
- `datetime_payload_from_time_context()`
- `AGENT_EVAL_FIXED_NOW`
- API/Agent/Workflow `override_now`
- `state["time_context_result"]` request cache

Eval 默认：

```text
2026-05-17 01:00:00 Asia/Shanghai
```

验证：

- fixed now 下 `明天` 为 `2026-05-18`
- fixed now 下 `下周` 为 `2026-05-18` 至 `2026-05-24`
- datetime tool 不返回 `days`
- 同一 state 多次相对日期解析只调用一次 datetime tool

## 6. Capability Registry Integration

实现：

- `ContractCapabilityHandler`
- `handler_names()`
- `visible_contracts(role=...)`
- `compile(ctx)`
- `validate(name, plan, ctx)`
- `resolve(name, plan, ctx)`
- `format_answer(name, results, ctx)`

Graph catalog 现在记录 role 可见 capability 名称。新增 capability 不需要再改 `graph/nodes.py`。

## 7. Planning Layer Cleanup

结果：

- `src/mini_rag/graph/planning_contract.py`: 12 行
- `src/mini_rag/planning/contract_normalizer.py`: 284 行

`graph/planning_contract.py` 不再 import calendar/attendance 领域细节，只保留兼容导出。

## 8. Nodes.py Cleanup

结果：

- `src/mini_rag/graph/nodes.py`: 60 行
- `src/mini_rag/orchestration/agentic_nodes.py`: 1999 行

说明：本轮已完成 graph boundary 瘦身。运行时实现仍有进一步拆服务空间，尤其是 retrieval/reflection/memory/trace，但不再堆在 `graph/nodes.py`。

## 9. Calendar / Attendance / RAG / Datetime Status

- Datetime：完成 fixed now、compact payload、request cache。
- Calendar：继续沿用上一轮 contract/compiler/resolver/validator/verifier/formatter/service 分层；写安全单测仍通过。
- Attendance：权限拒绝与异常明细语义保持稳定；修复的是 evaluator 对“无权查看/查询”的识别，不是 Agent case patch。
- RAG：保持 hybrid 默认；RAG clean full32 全部通过，没有为满分新增 source boost。

## 10. Answer Composer Status

工具类答案继续走模板：

- datetime
- calendar query/write
- attendance query
- permission/refusal/clarification

RAG 答案仍使用 LLM，但输入是 compact AnswerPacket/evidence，不把 raw state 或完整 raw tool result 塞进 answer prompt。

## 11. Test Results

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests -q
```

结果：

```text
214 passed in 75.51s
```

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m compileall -q src
```

结果：通过。

## 12. Eval Results

aligned 12:

```text
outputs/eval/final_aligned12_rule.json
executed_cases=12, infra_error_cases=0, agent_passed_cases=12, agent_failed_cases=0
```

V2 first20:

```text
outputs/eval/final_v2_first20_rule.json
executed_cases=20, infra_error_cases=0, agent_passed_cases=20, agent_failed_cases=0
```

RAG clean full32:

```text
outputs/eval/final_rag_clean_full32_rule.json
executed_cases=32, infra_error_cases=0, agent_passed_cases=32, agent_failed_cases=0
Recall/Citation/Refusal = 1.0
```

V2 full64:

```text
outputs/eval/final_v2_full64_rule.json
executed_cases=0, infra_error_cases=1, agent_failed_cases=0
```

说明：最终重跑在第 1 条遇到 DashScope free-tier quota exhausted。此前同一轮 full64 已跑到第 49 条，发现 `e2e_v2_att_005` 是 evaluator 拒绝识别漏判；已用通用规则修复并加单测。后续 RAG clean full32 又完整通过，说明 RAG 主链路未退化。

## 13. Remaining Failures and Root Cause

- `final_v2_full64_rule`: infra_error，DashScope `AllocationQuota.FreeTierOnly`，不计 Agent failure。
- 没有保留需要 case patch 的 Agent 失败。

## 14. What Was Not Fixed and Why

- 没有为了单个 eval case 写关键词补丁。
- 没有为 RAG 满分新增 source boost。
- 没有继续追 V2 full64 的 100%，因为最终阻塞是外部 quota。
- `orchestration/agentic_nodes.py` 仍较大，暂不在本轮继续大拆，以免在已通过测试/eval 后引入高风险重写。

## 15. Next Recommendations

1. 下一轮把 `orchestration/agentic_nodes.py` 中 retrieval/reflection/memory/trace 分别迁入 `retrieval/service.py`、`reflection/service.py`、`memory/service.py`、`observability/tracing.py`。
2. 给 V2 full64 在额度恢复后重跑完整报告。
3. 将 `CapabilityRegistry` 更深接入 planning compiler，让 graph/workflow 进一步只依赖 capability handler。
4. 对 latency 做 trace-based 优化，不跳过 validator/resolver。
