# Round10 Architecture Refactor Report

## 本阶段目标

按 `CODEX_AGENT_UPGRADE_PLAN.md` 继续做架构主线改造，不追求单个 eval case 满分：

- 让 compiler / validator / resolver / executor / answer composer 职责更清楚。
- 降低 `nodes.py`、`planning_contract.py`、`graph/time_contract.py` 的业务规则承载。
- 记录评测失败原因，不做关键词补丁或 case-by-case 修复。

## 主要架构变化

- `src/mini_rag/capabilities/calendar/lexicon.py`
  - 新增日历领域词表，避免 `calendar/compiler.py` 继续堆关键词。
- `src/mini_rag/capabilities/calendar/slots.py`
  - 新增日历文本槽位抽取：event type、relative query、ordinal、event_id、update fields。
- `src/mini_rag/capabilities/calendar/compiler.py`
  - 缩到 169 行，只做任务编译，不再直接维护领域词表和正则。
- `src/mini_rag/capabilities/calendar/resolver.py`
  - 接管原 `tools/calendar_resolution.py` 中的 selector、query-first update/delete、多候选安全解析逻辑。
- `src/mini_rag/tools/calendar_resolution.py`
  - 改为兼容 shim。
- `src/mini_rag/capabilities/datetime/resolver.py`
  - 接管原 `graph/time_contract.py` 中的 symbolic date、relative date range、weekday date resolution。
- `src/mini_rag/graph/time_contract.py`
  - 改为 5 行兼容 shim。
- `src/mini_rag/planning/compiler.py`
  - 接管 classification / plan / task 编译逻辑。
- `src/mini_rag/planning/gates.py`
  - 接管 capability-level gate：权限、日历缺槽、日历写目标、考勤范围。
- `src/mini_rag/execution/tool_executor.py`
  - 接管通用工具执行、权限检查、结果验证衔接、审计事件记录。
- `src/mini_rag/answer/packet.py`
  - 增加 `build_answer_packet()` 和 compact task results，answer prompt 不再直接吃 raw state。

## 瘦身结果

- `src/mini_rag/graph/planning_contract.py`: 约 672 行 -> 284 行。
- `src/mini_rag/graph/time_contract.py`: 约 497 行 -> 5 行 shim。
- `src/mini_rag/graph/nodes.py`: 本轮约 2031 行 -> 1979 行。

## 新增/更新测试

- `tests/test_calendar_compiler.py`
- `tests/test_calendar_domain_ownership.py`
- `tests/test_datetime_domain_ownership.py`
- `tests/test_planning_compiler.py`
- `tests/test_planning_capability_gates.py`
- `tests/test_tool_executor.py`
- `tests/test_answer_packet.py`
- `tests/test_prompt_input_structure.py`

## 运行结果

- `TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests -q`
  - Result: `202 passed in 81.43s`
- `scripts/agent_eval_suite_relaxed.py --suite e2e --questions eval/agent_eval_cases_full/agent_e2e_eval_cases_aligned.jsonl --judge rule --output outputs/eval/round10_aligned12_rule`
  - Result: `9/12 passed`, `infra_error_cases=0`
- `scripts/agent_eval_suite_relaxed.py --suite e2e --questions eval/agent_eval_cases_v2_comprehensive/eval/agent_e2e_comprehensive_v2.jsonl --judge rule --limit 20 --output outputs/eval/round10_v2_e2e_first20_rule`
  - Result: `20/20 passed`, `infra_error_cases=0`
- `scripts/agent_eval_suite_relaxed.py --suite rag --questions eval/rag_clean_eval_set/rag_clean_questions.jsonl --judge rule --limit 8 --mode hybrid --output outputs/eval/round10_rag_clean_sample8_rule`
  - Result: `8/8 passed`, `infra_error_cases=0`

## Round10 Eval 失败归因

- `e2e_tool_001`
  - 分类：评测题 / fixture 期望漂移。
  - 现象：Agent 先 query，下周团建为空，因此 update 安全 skipped，没有发生错误写入。
  - 暂不修原因：为了让它通过而伪造候选或强行写入会违反写安全原则。

- `e2e_tool_006`
  - 分类：evaluator wording/must-contain 严格。
  - 现象：Agent 查询明天会议为空，并补充 employee 无权删除/修改日程。
  - 暂不修原因：核心行为正确；不为 must_contain 词面写答案补丁。

- `e2e_tool_008`
  - 分类：fixture/date-assumption 依赖。
  - 现象：Agent 执行 datetime + calendar query；当前日期为 2026-05-18，明天为 2026-05-19，fixture 返回空，但 case 期待具体 `10:00-11:00`。
  - 暂不修原因：属于当前日期/fixture 与预期不一致，不应硬编码日期或会议。

## 清理

- 移动到 `old2/`：
  - `old2/pycache_20260518/`
  - `old2/test_cache_20260518/`
  - `old2/eval_outputs_20260518/`
- 保留当前可追踪报告：
  - `outputs/eval/round10_*`
  - `outputs/refactor_round10_architecture_report_20260518.md`

## 剩余风险

- `nodes.py` 仍接近 2000 行，RAG retrieval / reflection / memory update 还可继续拆。
- `tools/input_contract.py` 仍是工具入参适配入口，下一轮可迁到 `execution/tool_input.py` 或 capability adapter。
- aligned 12 的 3 个失败建议下一轮从 fixture/current-date/evaluator 角度处理，而不是写 Agent case patch。

## 下一阶段建议

1. 把 RAG retrieval execution 和 completion reflection 从 `nodes.py` 继续拆到 `capabilities/rag/service.py` 与 `execution/`.
2. 把 `tools/input_contract.py` 改为兼容 shim，主体迁到 execution/capability adapter。
3. 给 aligned 12 增加固定 TimeContext fixture，避免“当前日期变化”导致期望漂移。
