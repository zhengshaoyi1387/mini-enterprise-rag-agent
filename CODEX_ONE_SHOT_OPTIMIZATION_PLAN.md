# CODEX 一步到位优化计划：mini-enterprise-rag-agent

> 目标：不要继续追逐单个评测 case 的 100% 通过率。接下来一次性按架构主线完成收口：能力正确、时间可复现、职责清晰、节点瘦身、评测可信、代码干净。

---

## 0. 总原则

### 必须做

1. 先完整阅读：
   - `CODEX_AGENT_UPGRADE_PLAN.md`
   - `outputs/refactor_round10_architecture_report_20260518.md`
   - 当前源码结构
   - 现有 tests / eval / fixture
2. 先做架构收口，再做少量关键验证。
3. 允许部分刁钻 eval 暂时失败，但必须归因。
4. 每一大轮改完再测试，不要每改一个小点就跑 eval。
5. 所有改动必须围绕通用机制，不写 case-by-case patch。
6. 保持项目干净，废弃代码、旧输出、临时文件移动到 `old2/`。

### 禁止做

1. 禁止为了某个评测题写关键词硬编码。
2. 禁止继续往 `nodes.py` 堆业务逻辑。
3. 禁止继续往 `calendar/compiler.py` 无限加词表。
4. 禁止让 LLM 负责权限、日期最终换算、写操作目标选择、工具参数修复。
5. 禁止把 raw state / raw tool result 整包塞进 answer prompt。
6. 禁止为了性能跳过 validator / resolver / verifier。
7. 禁止把 infra error 算成 Agent 失败。
8. 禁止把评测满分当成唯一目标。

---

## 1. 当前状态判断

当前项目已经完成一轮架构拆分：

- `calendar/compiler.py` 已拆出 `lexicon.py / slots.py`。
- `graph/time_contract.py` 已变成 shim，主体迁到 `capabilities/datetime/resolver.py`。
- `planning_contract.py` 已从约 672 行降到约 284 行。
- 新增 `planning/compiler.py / gates.py`。
- 新增 `execution/tool_executor.py`。
- 新增或强化 `answer/packet.py`。
- 单测已达到 `202 passed`。
- V2 first20 和 RAG sample8 已通过。

但仍有核心缺口：

1. 相对时间评测会随真实日期漂移，缺少 fixed now。
2. 同一轮请求可能重复调用 `get_current_datetime`，缺少 request-level TimeContext cache。
3. `CapabilityRegistry` 仍偏 metadata，未真正统一驱动 compile / validate / resolve / format。
4. `nodes.py` 仍接近 2000 行，不是纯 LangGraph 编排层。
5. `planning_contract.py` 虽已瘦身，但仍承担过多 merge / validation / fallback 责任。
6. RAG full 与 complex task 还未系统收口。
7. aligned 12 当前 9/12，但其中部分失败来自时间基准和 fixture 假设漂移，不应盲目追修。

---

## 2. 本轮最终目标

本轮目标不是“评测 100%”，而是完成架构收口：

1. 时间可复现：eval 使用固定时间，生产使用真实时间。
2. 时间统一：同一请求只初始化一次 TimeContext。
3. 能力统一入口：CapabilityRegistry 真正接入主流程。
4. 节点瘦身：`nodes.py` 只做 LangGraph 编排。
5. Planning 收口：`planning_contract.py` 不再承担领域业务。
6. RAG 收口：RAG compiler / retriever / verifier / formatter 形成闭环。
7. Answer 收口：工具类回答模板化，LLM 只用于 RAG / synthesis。
8. Eval 收口：失败可归因，不被 infra / fixture / 文案误判污染。
9. 清理收口：旧代码、临时输出、无用文件进入 `old2/`。

---

## 3. Milestone 1：固定时间基准与 TimeContext 缓存

### 目标

解决所有相对日期随真实当前日期漂移的问题，并避免同一轮重复调用时间工具。

### 修改方向

新增或完善：

- `src/mini_rag/capabilities/datetime/resolver.py`
- `src/mini_rag/capabilities/datetime/service.py`
- `src/mini_rag/core/contracts.py`
- `src/mini_rag/graph/nodes.py`
- `scripts/agent_eval_suite.py`
- `scripts/agent_eval_suite_relaxed.py`

### 实现要求

1. 新增统一 `TimeContext`：

```python
class TimeContext(BaseModel):
    timezone: str
    now: datetime
    today: date
    yesterday: date
    tomorrow: date
    day_after_tomorrow: date
    this_week: DateRange
    last_week: DateRange
    next_week: DateRange
    this_month: DateRange
    last_month: DateRange
    next_month: DateRange
```

2. 支持 fixed now 注入：

优先级：

```text
request.override_now
> eval config / env AGENT_EVAL_FIXED_NOW
> settings.fixed_now
> datetime.now(timezone)
```

3. Eval 默认固定：

```text
2026-05-17 01:00:00 Asia/Shanghai
```

4. 生产环境默认真实当前时间。

5. 同一轮 request 只初始化一次 TimeContext。

6. `get_current_datetime` 后续任务复用 TimeContext，不重复计算。

7. 所有 `date/start_date/end_date` 进入工具前必须是 `YYYY-MM-DD`。

8. 不允许以下值进入真实工具：

```text
today
tomorrow
today + 1 day
next_week
${tomorrow}
下周
后天
```

### 新增测试

- `tests/test_time_context_fixed_now.py`
- `tests/test_time_context_cache.py`
- `tests/test_datetime_domain_ownership.py`

### 验收

1. 固定 now 下，`明天` 永远解析为 `2026-05-18`。
2. 固定 now 下，`下周` 永远解析为 `2026-05-18 至 2026-05-24`。
3. 同一请求中 `get_current_datetime` 不重复执行。
4. eval 不再因真实日期变化而漂移。

---

## 4. Milestone 2：CapabilityRegistry 真正接入主流程

### 目标

把 CapabilityRegistry 从“契约登记表”升级为统一能力入口。

### 修改方向

新增或完善：

- `src/mini_rag/capabilities/base.py`
- `src/mini_rag/capabilities/registry.py`
- `src/mini_rag/capabilities/calendar/*`
- `src/mini_rag/capabilities/attendance/*`
- `src/mini_rag/capabilities/datetime/*`
- `src/mini_rag/capabilities/rag/*`
- `src/mini_rag/planning/compiler.py`
- `src/mini_rag/planning/gates.py`

### 统一接口

每个 capability handler 至少实现：

```python
class CapabilityHandler(Protocol):
    name: str
    contract: CapabilityContract

    def compile(self, ctx: RequestContext) -> CandidatePlan | None: ...
    def validate(self, plan: CandidatePlan, ctx: RequestContext) -> ValidationResult: ...
    def resolve(self, plan: CandidatePlan, ctx: RequestContext) -> ExecutablePlan | ValidationResult: ...
    def format_result(self, result: TaskResult, ctx: RequestContext) -> AnswerPacket | None: ...
```

### Registry 行为

1. `CapabilityRegistry` 负责：
   - 注册 handler
   - 按 capability name 获取 handler
   - 暴露可见能力
   - 根据 role 过滤能力
   - 提供统一 compile / validate / resolve / format 入口

2. Graph / planning 层不得直接 import calendar / attendance 细节。

3. 新增能力时不应修改 `nodes.py`。

### 新增测试

- `tests/test_capability_registry.py`
- `tests/test_capability_registry_integration.py`

### 验收

1. Calendar / Attendance / Datetime / RAG 全部通过 registry 访问。
2. `nodes.py` 不直接写 capability 业务规则。
3. 新增 capability 只需注册 handler。

---

## 5. Milestone 3：Planning 层收口

### 目标

让 `planning_contract.py` 不再成为第二个上帝文件。

### 修改方向

拆分为：

```text
src/mini_rag/planning/compiler.py
src/mini_rag/planning/gates.py
src/mini_rag/planning/plan_merge.py
src/mini_rag/planning/route_normalizer.py
src/mini_rag/planning/permission_gate.py
src/mini_rag/planning/domain_validation.py
src/mini_rag/planning/context_policy.py
```

`graph/planning_contract.py` 仅保留兼容 facade，最终目标低于 120 行。

### 职责边界

1. `compiler.py`：把 classification / LLM plan / capability compile 合并为 CandidatePlan。
2. `gates.py`：决定是否需要 build_plan LLM。
3. `plan_merge.py`：只做结构合并，不做领域业务。
4. `route_normalizer.py`：route / intent / action 归一化。
5. `permission_gate.py`：权限门禁。
6. `domain_validation.py`：委托 registry 对应 capability validator。
7. `context_policy.py`：控制 planner / answer 能看到哪些上下文。

### 禁止

1. 不要在 planning 层解析“第一个会议”“迟到”“团建”。
2. 不要在 planning 层修 event_id。
3. 不要在 planning 层做具体工具业务。

### 新增测试

- `tests/test_planning_compiler.py`
- `tests/test_planning_capability_gates.py`
- `tests/test_planning_contract_facade.py`

### 验收

1. `planning_contract.py` 低于 120 行。
2. planning 层只做结构归一化和能力委托。
3. domain 逻辑全部迁到 capabilities。

---

## 6. Milestone 4：nodes.py 瘦身为 LangGraph 编排层

### 目标

`nodes.py` 不再承载业务逻辑，只负责调用服务。

### 修改方向

新增或完善：

```text
src/mini_rag/execution/tool_executor.py
src/mini_rag/execution/task_graph.py
src/mini_rag/execution/result_assembler.py
src/mini_rag/retrieval/service.py
src/mini_rag/reflection/service.py
src/mini_rag/memory/service.py
src/mini_rag/answer/composer.py
```

### 从 nodes.py 迁出

1. RAG retrieval 执行逻辑 -> `retrieval/service.py` 或 `capabilities/rag/retriever.py`
2. completion reflection -> `reflection/service.py`
3. tool execution -> `execution/tool_executor.py`
4. task result assembly -> `execution/result_assembler.py`
5. answer formatting -> `answer/composer.py`
6. memory update -> `memory/service.py`
7. trace building -> `observability/tracing.py`

### nodes.py 最终保留

```python
def load_context(...): ...
def classify_intent(...): ...
def build_plan(...): ...
def validate_plan(...): ...
def route(...): ...
def execute(...): ...
def generate_answer(...): ...
def update_memory(...): ...
```

每个函数只做委托，不写领域细节。

### 验收

1. `nodes.py` 目标低于 800 行。
2. 不出现大量 calendar / attendance / RAG 领域规则。
3. 不直接拼复杂 answer。
4. 不直接操作 raw tool result 构造最终 prompt。

---

## 7. Milestone 5：Calendar 能力收口

### 目标

Calendar 形成完整 domain service，而不是 compiler 规则集合。

### 修改方向

完善：

```text
src/mini_rag/capabilities/calendar/contract.py
src/mini_rag/capabilities/calendar/lexicon.py
src/mini_rag/capabilities/calendar/slots.py
src/mini_rag/capabilities/calendar/compiler.py
src/mini_rag/capabilities/calendar/resolver.py
src/mini_rag/capabilities/calendar/validator.py
src/mini_rag/capabilities/calendar/verifier.py
src/mini_rag/capabilities/calendar/formatter.py
src/mini_rag/capabilities/calendar/service.py
```

### 拆出明确组件

1. `CalendarIntentResolver`
2. `CalendarSelectorParser`
3. `UpdateFieldExtractor`
4. `CalendarTargetResolver`
5. `CalendarWriteSafetyValidator`
6. `CalendarResultVerifier`
7. `CalendarAnswerFormatter`

### 核心规则

1. 缺槽 create/update/delete 必须澄清。
2. 多候选 update/delete 必须澄清，除非用户明确全部或第 N 个。
3. `event_id=all/multiple/from_x/*` 禁止进入真实写工具。
4. 真实 `EVT-YYYYMMDD-NNNN` 可以进入工具，由工具返回存在/不存在。
5. 查询类不能被 compiler 偷偷追加 update task。
6. 疑问句 / 条件句 / 能力询问不能触发写操作。

### 新增负例测试

```text
能不能把第一个会议改成10点
如果把第一个会议改成10点会怎样
查一下第一个会议是不是10点
有没有办法修改会议
为什么不能 event_id=all 删除
```

这些都不能真实写入。

### 验收

1. Calendar compiler 不继续无限加词表。
2. selector / update field / intent 明确分层。
3. 写操作安全 case 全部稳定。

---

## 8. Milestone 6：Attendance 能力收口

### 目标

Attendance 查询稳定，权限清晰，答案不靠 LLM 编统计。

### 修改方向

完善：

```text
src/mini_rag/capabilities/attendance/contract.py
src/mini_rag/capabilities/attendance/compiler.py
src/mini_rag/capabilities/attendance/validator.py
src/mini_rag/capabilities/attendance/verifier.py
src/mini_rag/capabilities/attendance/formatter.py
src/mini_rag/capabilities/attendance/service.py
```

### 必须确认权限

明确 finance / it 是否允许查考勤：

- 如果允许：只允许低敏或个人范围。
- 如果不允许：从 registry / contract / eval 中同步移除。

不得出现权限表允许、validator 又拒绝的冲突。

### 核心规则

1. 异常 = `late + leave + absent`。
2. 明细 / 名单 / 记录 / 具体人员 => `include_records=true`。
3. 日期范围必须来自 TimeContext / absolute date。
4. 不允许 LLM 猜 2024 之类错误年份通过。
5. 统计结果由工具 / formatter 输出，LLM 不重新计算。

### 验收

1. attendance subset 稳定通过。
2. 权限行为和 contract 一致。
3. 答案不篡改统计结果。

---

## 9. Milestone 7：RAG 能力收口

### 目标

RAG full32 不退化，E2E RAG 段能区分 evaluator 问题和真实检索问题。

### 修改方向

完善：

```text
src/mini_rag/capabilities/rag/compiler.py
src/mini_rag/capabilities/rag/retriever.py
src/mini_rag/capabilities/rag/verifier.py
src/mini_rag/capabilities/rag/formatter.py
src/mini_rag/retrieval/retriever.py
```

### 必须处理

1. RAG query compiler 根据问题选择正确 KB scope。
2. 财务报销 / 差旅问题必须优先 finance。
3. HR 制度问题必须优先 hr。
4. IT 权限 / VPN / 账号问题必须优先 it。
5. 产品相关问题必须优先 product。
6. public 只处理公开制度 / 通用信息。
7. 不要只靠标题 boost 掩盖 KB 路由错误。
8. 无证据必须拒答。
9. 工具答案不得伪造 RAG citation。

### Evaluator 修复

区分：

```text
真实拒答
政策内容中出现“无权限 / 不能访问”
答案说“没有直接找到，但根据片段可以...”
答案确实缺证据
```

不要把政策描述里的“无权限”误判成 Agent refusal。

### 验收

1. RAG clean full32 跑完并输出归因。
2. 真实检索失败要修 compiler / retriever。
3. evaluator 误判要修 evaluator。
4. 不要求无脑 100%，但必须说明每条失败性质。

---

## 10. Milestone 8：Answer Composer 收口

### 目标

工具做对时，最终答案不能再说错。

### 修改方向

完善：

```text
src/mini_rag/answer/packet.py
src/mini_rag/answer/composer.py
src/mini_rag/answer/templates.py
src/mini_rag/answer/llm_answer.py
src/mini_rag/graph/prompts.py
```

### 回答策略

1. Datetime：模板回答。
2. Calendar query/write：模板回答。
3. Attendance：模板回答。
4. Permission/refusal/clarification：模板回答。
5. RAG：LLM answer，但只看 evidence packet。
6. Mixed：AnswerPacket synthesis，不吃 raw state。

### 禁止

1. LLM 自己计算星期。
2. LLM 自己判断写操作是否成功。
3. LLM 自己重新统计考勤。
4. LLM 看到完整 raw tool JSON。
5. LLM 看到完整 previous_tool_context，除非 context_policy 允许。

### 验收

1. Answer prompt 输入稳定、短、结构化。
2. 工具类回答不调用 LLM 或只在必要时调用。
3. 最终答案不篡改 tool result。

---

## 11. Milestone 9：评测体系收口

### 目标

评测用于诊断，不用于诱导 case patch。

### 修改方向

完善：

```text
scripts/agent_eval_suite.py
scripts/agent_eval_suite_relaxed.py
src/mini_rag/evaluation/*
```

### 统一两套脚本

两套脚本必须共享：

1. normalize answer
2. infra error detection
3. fixture restore
4. trajectory metrics
5. date / time / weekday normalization
6. empty result normalization
7. refusal detection

### 失败分类

每条失败必须归因：

```text
agent_router_error
agent_planner_error
agent_validator_error
agent_resolver_error
agent_executor_error
agent_answer_error
rag_retrieval_error
evaluator_error
fixture_drift
infra_error
case_too_adversarial
```

### 注意

`cannot import name` 不能一律算 infra。必须区分：

1. 外部依赖缺失：infra。
2. 项目代码 import regression：agent/code regression。

### 验收

1. aligned / V2 / RAG 报告有失败归因。
2. infra 不计入 Agent failure。
3. fixture 每条 case 默认恢复。
4. 可以明确说明哪些 case 暂时不修。

---

## 12. Milestone 10：清理 old2

### 目标

项目保持干净。

### 移动到 old2

1. 旧 eval 输出。
2. 临时调试脚本。
3. `__pycache__`。
4. `.pytest_cache`。
5. 废弃兼容文件。
6. 不再被 import 的旧 helper。
7. 旧报告，只保留最新关键报告。

### 禁止

1. 不要删除仍被 import 的文件。
2. 不要移动 fixture / eval case / source data。
3. 不要移动当前报告。
4. 不要移动必要测试。

### 验收

1. `pytest tests -q` 通过。
2. `python -m compileall src` 通过。
3. `grep` / import 检查没有指向 old2 的依赖。

---

## 13. 测试与评测节奏

### 每个小模块后只跑对应单测

例如：

```bash
pytest tests/test_time_context_fixed_now.py -q
pytest tests/test_capability_registry.py -q
pytest tests/test_planning_compiler.py -q
```

### 每个大 Milestone 后跑核心单测集合

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest \
  tests/test_capability_registry.py \
  tests/test_planning_compiler.py \
  tests/test_planning_capability_gates.py \
  tests/test_calendar_compiler.py \
  tests/test_calendar_domain_validator.py \
  tests/test_datetime_domain_ownership.py \
  tests/test_tool_executor.py \
  tests/test_answer_packet.py \
  tests/test_agent_eval_suite_relaxed.py \
  -q
```

### 全部改造完成后再跑完整测试

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests -q
```

### 最终评测只跑这几组

```bash
# aligned 12
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --questions eval/agent_eval_cases_full/agent_e2e_eval_cases_aligned.jsonl \
  --judge rule \
  --output outputs/eval/final_aligned12_rule

# V2 first20
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --questions eval/agent_eval_cases_v2_comprehensive/eval/agent_e2e_comprehensive_v2.jsonl \
  --judge rule \
  --limit 20 \
  --output outputs/eval/final_v2_first20_rule

# V2 full64，允许 infra 单独统计
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --questions eval/agent_eval_cases_v2_comprehensive/eval/agent_e2e_comprehensive_v2.jsonl \
  --judge rule \
  --output outputs/eval/final_v2_full64_rule

# RAG clean full32
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/agent_eval_suite_relaxed.py \
  --suite rag \
  --questions eval/rag_clean_eval_set/rag_clean_questions.jsonl \
  --judge rule \
  --mode hybrid \
  --output outputs/eval/final_rag_clean_full32_rule
```

### 不要做

1. 不要每失败一个 case 就马上局部修。
2. 不要为了 aligned 12 满分牺牲架构。
3. 不要为了 RAG 满分乱加 source boost。
4. 不要为了 V2 full64 满分写 case patch。

---

## 14. 最终验收标准

### 必须满足

1. `pytest tests -q` 通过。
2. fixed now 生效，eval 时间不漂移。
3. 同一请求 TimeContext 不重复初始化。
4. `CapabilityRegistry` 统一接入 compile / validate / resolve / format。
5. `planning_contract.py` 低于 120 行或仅作为兼容 facade。
6. `nodes.py` 明显瘦身，目标低于 800 行。
7. `graph/time_contract.py` 保持 shim，不回填业务逻辑。
8. Calendar / Attendance / Datetime / RAG 领域逻辑在 capabilities 下。
9. Tool execution 在 execution 层。
10. Answer composer 独立，不吃 raw state。
11. Eval 报告区分 infra / evaluator / fixture / agent 真实错误。
12. old2 清理完成，项目无明显临时垃圾。

### 可以暂时不满足，但必须报告

1. aligned 12 不是 12/12。
2. V2 full64 不是 100%。
3. RAG clean full32 不是 100%。
4. 部分 adversarial case 暂不修。
5. 外部 LLM quota / infra 阻塞。

### 报告必须说明

1. 哪些失败是真实 Agent 能力问题。
2. 哪些失败是 evaluator 误判。
3. 哪些失败是 fixture / 时间假设问题。
4. 哪些失败是 case 过度刁钻。
5. 哪些失败因为 quota / infra 未执行。

---

## 15. 最终报告格式

完成后写入：

```text
outputs/final_architecture_refactor_report_YYYYMMDD.md
```

报告必须包含：

```markdown
# Final Architecture Refactor Report

## 1. Summary

## 2. Architecture Changes

## 3. Files Changed

## 4. Removed / Moved to old2

## 5. TimeContext / Fixed Now

## 6. Capability Registry Integration

## 7. Planning Layer Cleanup

## 8. Nodes.py Cleanup

## 9. Calendar / Attendance / RAG / Datetime Status

## 10. Answer Composer Status

## 11. Test Results

## 12. Eval Results

## 13. Remaining Failures and Root Cause

## 14. What Was Not Fixed and Why

## 15. Next Recommendations
```

---

## 16. 本轮执行口令

请直接开始执行，不要再只写计划。

执行顺序：

```text
1. fixed now + TimeContext cache
2. CapabilityRegistry 接入
3. planning_contract.py 拆分收口
4. nodes.py 瘦身
5. calendar / attendance / rag / datetime domain 收口
6. answer composer 收口
7. eval 归因收口
8. old2 清理
9. 全量测试
10. 最终评测
11. 最终报告
```

如果遇到失败：

```text
先归因，再决定是否修。
不要为了某个评测 case 写补丁。
不要因为某个刁钻 case 阻塞架构主线。
```

最终目标：

```text
架构完整 > 能力正确 > 安全可靠 > 评测可信 > 性能优化 > 评测满分
```
