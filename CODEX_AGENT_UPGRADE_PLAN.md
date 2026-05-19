# mini-enterprise-rag-agent 能力正确性优先重构升级任务书（给 Codex 执行）

> 项目：`zhengshaoyi1387/mini-enterprise-rag-agent`  
> 当前源码包：`mini-enterprise-rag-agent-enterprise-langgraph-expanded-kb (3).zip`  
> 目标：把当前课程 Demo 风格的 LangGraph Agentic RAG 项目，重构成“能力边界清晰、执行正确、安全可控、评测可信、性能可解释”的企业级 Agent。  
> 第一优先级：能力正确性与安全性。  
> 第二优先级：评测可信与问题可定位。  
> 第三优先级：结构解耦。  
> 第四优先级：性能优化。  
>
> 严禁一开始为了降低延迟写 fast path / 关键词补丁 / 针对样例的 if-else。低延迟只能作为正确架构自然产生的结果。

---

## 0. Codex 必须遵守的总原则

### 0.1 绝对禁止

1. 不要为了通过某个 case 写关键词匹配补丁。
2. 不要把新的业务规则继续塞进 `src/mini_rag/graph/nodes.py`。
3. 不要让 LLM 决定权限、最终日期、星期、写操作目标、多个候选中选哪个。
4. 不要让工具接收 `today`、`tomorrow`、`today + 1 day`、`next_week`、`下周` 这类 symbolic date。
5. 不要让 `event_id=all`、`event_id=multiple`、`event_id_from_x`、`*` 进入真实 update/delete 工具。
6. 不要把完整 raw tool result、完整 datetime ranges、days 数组、完整 previous context 重新塞给 answer prompt。
7. 不要把 infra error 当成 Agent 失败。
8. 不要只修改 prompt 来解决执行安全问题。
9. 不要一次性重写整个项目导致现有测试全部失效。必须分阶段、小步提交、每步可测。

### 0.2 必须坚持

1. 能力正确性优先于响应速度。
2. Graph node 只做编排，不做领域业务规则。
3. 每类能力要有 contract、compiler、validator、resolver、formatter。
4. 写操作必须经过权限、缺槽、日期、selector、多候选、结果验证门禁。
5. 每条失败 case 必须能归因到 router / planner / validator / resolver / executor / answer / evaluator / infra 中的一层。
6. 每个阶段必须新增或更新测试。
7. 每个阶段必须运行测试，并在最终报告里列出命令和结果。
8. 保持代码简单，不要为了“企业级”制造复杂抽象。

---

## 1. 当前项目事实与问题摘要

### 1.1 当前主链路

当前 LangGraph 主链路大致是：

```text
load_context
-> check_permission
-> build_capability_catalog
-> build_planning_context
-> classify_intent
-> build_plan
-> validate_plan
-> route
-> plan_retrieval / call_tool
-> completion_reflect
-> generate_answer
-> update_memory
```

`workflow.py` 当前固定把 `classify_intent` 接到 `build_plan`，导致很多简单任务也必须经过第二次规划 LLM。

### 1.2 当前源码结构风险

当前文件规模约为：

```text
src/mini_rag/graph/nodes.py              2422 行
src/mini_rag/graph/prompts.py             777 行
src/mini_rag/graph/planning_contract.py   593 行
src/mini_rag/graph/time_contract.py       331 行
src/mini_rag/tools/calendar_resolution.py 396 行
src/mini_rag/tools/input_contract.py      184 行
scripts/agent_eval_suite_relaxed.py      1353 行
```

这说明之前已经做过一次拆分，但仍然没有根治问题：复杂度只是从 `nodes.py` 搬到 `planning_contract.py`、`time_contract.py`、`calendar_resolution.py`、`input_contract.py`，主链路仍然由重 planner 驱动。

### 1.3 当前真实问题不是单纯“慢”

当前最核心问题是 Agent 能力不稳定：

1. 有时不知道该不该调用工具。
2. 有时调用了工具，但参数不稳定。
3. 有时工具执行对象错。
4. 有时应该澄清，却直接写入。
5. 有时工具结果是对的，最终回答又编错。
6. 有时评测失败，不知道是 Agent 错、评测器错，还是 API/LLM 额度错误。

所以不要先追求“几秒响应”。先让 Agent 做对事。

---

## 2. 参考架构原则

以下原则来自成熟 Agent / workflow 框架的共性，不要求引入这些框架，只吸收设计思想：

1. LangGraph：Graph 负责状态流、节点和条件边；节点应该是函数式编排单元，不应承载日历、考勤、时间解析等具体业务规则。
2. OpenAI Agents SDK：工具调用应有 tool guardrails，工具执行前检查输入、执行后检查输出；安全不能只靠 prompt。
3. Haystack Pipeline：组件只接收被显式连接的输入，不应访问全局上下文；这能提高调试性和减少上下文污染。
4. Pydantic AI：生产 Agent 应依赖类型安全、依赖注入、结构化输出和 evals；不要让 dict 在系统里无约束流动。

在本项目中落地为：

```text
LLM 负责：语义理解、复杂任务拆解、RAG 自然语言生成。
Python 负责：权限、日期换算、星期、工具参数合法性、selector、安全写入、结果验证。
LangGraph 负责：状态流编排。
Domain Service 负责：日历、考勤、RAG、时间等领域逻辑。
Evaluator 负责：区分能力错误、评测错误、infra 错误。
```

---

## 3. 目标架构：Capability-first Agent

### 3.1 能力分类

把当前 Agent 能力明确分为 6 类：

```text
A. Direct / Smalltalk / Time
   - 当前日期、时间、星期
   - 简单能力说明
   - 不需要企业知识库的问题

B. RAG QA
   - 企业制度问答
   - 多知识库检索
   - 引用忠实回答
   - 无证据拒答

C. Calendar Query
   - 查日程
   - 相对日期
   - 事件类型过滤
   - 多结果展示

D. Calendar Write
   - 创建日程
   - 修改日程
   - 删除日程
   - query-first update/delete
   - 多候选安全澄清

E. Attendance Query
   - 部门统计
   - 异常统计
   - 明细记录
   - 多状态组合

F. Mixed Task
   - RAG + 工具
   - 多工具
   - 多子任务
   - 上下文追问
```

### 3.2 新链路目标

新链路应逐步演进为：

```text
Request Intake
-> Capability Router
-> Capability Compiler
-> Plan Validator
-> Task Resolver
-> Executor
-> Result Verifier
-> Answer Composer
-> Memory Update
```

注意：

1. `Planner` 不再是系统中心。
2. `Capability Contract + Validator + Resolver` 才是系统中心。
3. `build_plan` 只用于复杂 mixed task，不能默认支配所有请求。

---

## 4. 建议新增或演进的模块

不要一次性全建空架子。按里程碑逐步添加。

### 4.1 core 能力模型

建议新增：

```text
src/mini_rag/core/capability.py
src/mini_rag/core/plan.py
src/mini_rag/core/validation.py
src/mini_rag/core/result.py
```

最小模型建议：

```python
from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class CapabilityName(str, Enum):
    DIRECT = "direct"
    DATETIME = "datetime"
    RAG = "rag"
    CALENDAR = "calendar"
    ATTENDANCE = "attendance"
    MIXED = "mixed"


class RiskLevel(str, Enum):
    LOW = "low"
    READ = "read"
    WRITE = "write"
    HIGH = "high"


class AnswerPolicy(str, Enum):
    TEMPLATE = "template"
    RAG_GROUNDED = "rag_grounded"
    SYNTHESIS = "synthesis"
    CLARIFICATION = "clarification"
    REFUSAL = "refusal"


class MissingSlot(BaseModel):
    name: str
    reason: str = ""


class PlannedTask(BaseModel):
    task_id: str
    kind: Literal["tool", "rag", "direct"]
    capability: CapabilityName
    objective: str
    tool: str | None = None
    action: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class CandidatePlan(BaseModel):
    capability: CapabilityName
    intent: str
    tasks: list[PlannedTask] = Field(default_factory=list)
    missing_slots: list[MissingSlot] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    answer_policy: AnswerPolicy = AnswerPolicy.TEMPLATE
    reason: str = ""


class ValidationIssue(BaseModel):
    code: str
    message: str
    task_id: str | None = None
    blocking: bool = True


class ValidationResult(BaseModel):
    status: Literal["valid", "needs_clarification", "refused", "skipped", "invalid"]
    issues: list[ValidationIssue] = Field(default_factory=list)
    safe_tasks: list[PlannedTask] = Field(default_factory=list)
    user_message: str | None = None


class TaskResult(BaseModel):
    task_id: str
    capability: CapabilityName
    action: str
    status: Literal["success", "skipped", "needs_clarification", "refused", "failed"]
    payload: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    error: str | None = None
```

可以先只新增模型和单测，不强行改完整链路。

### 4.2 capability registry

建议新增：

```text
src/mini_rag/capabilities/base.py
src/mini_rag/capabilities/registry.py
```

接口：

```python
from typing import Protocol

class CapabilityHandler(Protocol):
    name: str

    def compile(self, ctx) -> CandidatePlan | None:
        ...

    def validate(self, plan: CandidatePlan, ctx) -> ValidationResult:
        ...

    def resolve(self, plan: CandidatePlan, ctx) -> CandidatePlan | ValidationResult:
        ...

    def format_answer(self, results: list[TaskResult], ctx) -> str | None:
        ...
```

重要：

- Graph 不要知道日历、考勤细节。
- 新增报销、审批、工单工具时，不应该再改 `nodes.py`。

---

## 5. Milestone 0：先冻结基线，建立可定位评测

### 5.1 目标

在大改业务逻辑前，先让评测报告可信，能区分：

```text
router 错
planner 错
validator 错
resolver 错
executor 错
answer 错
evaluator 错
infra 错
```

### 5.2 修改文件

优先修改：

```text
scripts/agent_eval_suite_relaxed.py
tests/test_agent_eval_suite_relaxed.py
```

必要时新增：

```text
tests/test_eval_fixture_restore.py
tests/test_eval_infra_errors.py
```

### 5.3 要实现的能力

#### 5.3.1 infra_error 单独统计

识别以下错误为 infra error，不计入 Agent failure：

```text
AllocationQuota.FreeTierOnly
free tier of the model has been exhausted
Error code: 403
invalid_api_key
RateLimitError
APIConnectionError
ConnectTimeout
ReadTimeout
```

评测报告输出必须包含：

```json
{
  "total_cases": 64,
  "executed_cases": 33,
  "infra_error_cases": 31,
  "agent_passed": 20,
  "agent_failed": 13,
  "agent_pass_rate": "20/33"
}
```

如果连续遇到 quota/auth 类 infra error，默认停止后续 case，避免把后续全部记成 Agent 错。可增加参数：

```text
--stop-on-infra-error / --no-stop-on-infra-error
```

#### 5.3.2 默认 rule judge

默认不要跑 `judge=both`。LLM judge 会消耗额度并污染性能统计。

新增参数：

```text
--judge-sample-rate 0.0
--judge-failed-only
```

默认：

```text
--judge rule
```

#### 5.3.3 fixture restore

每条 case 前默认恢复：

```text
data/business/company_calendar.json
data/business/attendance.csv
```

建议新增基准 fixture：

```text
data/fixtures/company_calendar.base.json
data/fixtures/attendance.base.csv
```

如果基准 fixture 不存在，第一次运行测试时不要自动覆盖真实数据；应报错并提示创建。可以提供脚本或函数显式初始化。

评测参数：

```text
--restore-fixtures / --no-restore-fixtures
```

默认 `--restore-fixtures`。

#### 5.3.4 规则归一化

在 evaluator 中增加 normalize：

```text
日期：2026年5月18日 == 2026-05-18
时间：10:00–12:00 == 10:00-12:00
星期：Sunday / 周日 / 星期天 == 星期日
空结果：暂无公司日程 / 没有公司会议 / 无相关日程 == empty_result
地点：会议室 A == 会议室A
```

但注意：

- 归一化只用于评测判断。
- 不要为了评测归一化去改业务答案。

### 5.4 验收

运行：

```bash
pytest tests/test_agent_eval_suite_relaxed.py -q
pytest tests/test_eval_fixture_restore.py tests/test_eval_infra_errors.py -q
```

再运行小批量评测：

```bash
python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --questions eval/agent_eval_cases_v2_comprehensive/eval/agent_e2e_comprehensive_v2.jsonl \
  --judge rule \
  --limit 20 \
  --output outputs/eval/e2e_v2_rule_first20
```

报告中必须区分 `executed_cases`、`infra_error_cases`、`agent_failed_cases`。

---

## 6. Milestone 1：日期与 TimeContext 硬门禁

### 6.1 目标

任何进入工具层的日期都必须是绝对日期：

```text
YYYY-MM-DD
```

禁止进入工具层：

```text
today
tomorrow
yesterday
today + 1 day
today + 2 days
next_week
last_week
下周
后天
```

### 6.2 修改文件

优先在现有模块上演进，不必立刻重建大目录：

```text
src/mini_rag/graph/time_contract.py
src/mini_rag/tools/input_contract.py
src/mini_rag/tools/datetime_tool.py
src/mini_rag/graph/nodes.py     # 只允许接入，不允许新增大量业务规则
tests/test_daily_tools.py
tests/test_planner_contract_validation.py
```

可以新增：

```text
src/mini_rag/capabilities/datetime_context.py
tests/test_time_contract_gate.py
```

### 6.3 要实现的规则

#### 6.3.1 TimeContext

定义 request-level TimeContext，至少包含：

```text
now
timezone
today
yesterday
tomorrow
day_after_tomorrow
this_week
last_week
next_week
```

自然周定义：

```text
this_week = 当前自然周，周一到周日
last_week = 上一个完整自然周，周一到周日
next_week = 下一个完整自然周，周一到周日
```

以 `2026-05-17 星期日 Asia/Shanghai` 为例：

```text
this_week = 2026-05-11 至 2026-05-17
last_week = 2026-05-04 至 2026-05-10
next_week = 2026-05-18 至 2026-05-24
```

#### 6.3.2 工具入参日期门禁

在工具调用前统一检查：

```python
DATE_FIELDS = {"date", "start_date", "end_date"}
```

如果 task/tool_input 中这些字段不是 `YYYY-MM-DD`：

- 能确定性解析：改成绝对日期。
- 不能确定性解析：ValidationResult = `needs_clarification` 或 `invalid`。
- 绝不能继续调用真实工具。

#### 6.3.3 不再输出 days 数组

`get_current_datetime` 不允许返回几个月每天映射。

允许返回：

```json
{
  "date": "2026-05-17",
  "time": "18:00:00",
  "weekday_zh": "星期日",
  "timezone": "Asia/Shanghai",
  "ranges": {
    "this_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
    "last_week": {"start_date": "2026-05-04", "end_date": "2026-05-10"},
    "next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}
  }
}
```

不要返回：

```json
{"days": [...]}
```

### 6.4 测试必须覆盖

新增测试：

1. `today + 1 day` 不会进入工具。
2. `today + 2 days` 不会进入工具。
3. `next_week` 不会进入工具。
4. `last_week` 语义正确。
5. 同一句多个相对日期能分别解析。
6. datetime tool 不返回 days。
7. answer prompt 不包含完整 datetime raw JSON。

示例测试名：

```text
test_tool_input_rejects_symbolic_date_fields
test_today_plus_one_day_is_resolved_before_tool_call
test_last_week_means_previous_full_natural_week
test_datetime_tool_does_not_return_days_array
```

---

## 7. Milestone 2：Plan Validator 变成真正执行门禁

### 7.1 目标

`validate_plan` 不再只是“修一下 payload”，而是决定是否允许执行。

如果：

```text
missing_required_slots 非空
权限不足
日期不合法
写操作 target 未解析
多候选未澄清
event_id 非真实 EVT-... ID
```

则 executor 不得调用真实写工具。

### 7.2 修改文件

```text
src/mini_rag/graph/planning_contract.py
src/mini_rag/tools/input_contract.py
src/mini_rag/tools/calendar_resolution.py
src/mini_rag/graph/nodes.py
tests/test_planner_contract_validation.py
tests/test_execution_plan_completion.py
```

建议新增：

```text
tests/test_plan_validation_gate.py
```

### 7.3 必须实现的规则

#### 7.3.1 缺槽门禁

例如：

```text
用户：创建一个公司会议。
```

缺少：

```text
date
time/title 或 start_time/end_time
location 可选但如果工具必需则要澄清
```

正确行为：

```text
ValidationResult.status = needs_clarification
不调用 manage_company_calendar.create
最终回答要求用户补充日期、时间、主题等必要信息
```

#### 7.3.2 权限门禁

普通 employee 不能：

```text
manage_company_calendar.create
manage_company_calendar.update
manage_company_calendar.delete
```

应该：

```text
refused
不调用真实写工具
```

但如果用户问：

```text
查询明天会议，并告诉我能不能删除
```

应该允许 query，同时说明无权 delete。不要把整个请求当失败。

#### 7.3.3 写操作 event_id 门禁

真实写操作只允许：

```text
EVT-YYYYMMDD-NNNN
```

禁止：

```text
all
multiple
event_id_from_previous_query
event_id_from_context
*
空字符串
```

如果出现这些值，必须转入 resolver 或 clarification，不能进入工具。

### 7.4 验收

新增测试至少覆盖：

```text
缺槽 create 不调用工具
employee update/delete 被拒绝且不调用工具
event_id=all/multiple 不进入真实工具
日期字段不合法不进入真实工具
```

---

## 8. Milestone 3：CalendarDomain 重构，先解决最危险能力

### 8.1 目标

把日历写操作安全从 `nodes.py` / prompt / 零散 helper 中下沉到 CalendarDomain。

### 8.2 建议新增模块

```text
src/mini_rag/capabilities/calendar/__init__.py
src/mini_rag/capabilities/calendar/models.py
src/mini_rag/capabilities/calendar/resolver.py
src/mini_rag/capabilities/calendar/validator.py
src/mini_rag/capabilities/calendar/formatter.py
```

先不要急着把旧 `tools/calendar_resolution.py` 删除。可以先让新模块调用/包裹旧逻辑，再逐步迁移。

### 8.3 CalendarSelector 模型

```python
from pydantic import BaseModel

class CalendarSelector(BaseModel):
    event_id: str | None = None
    date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    event_type: str | None = None
    title_contains: str | None = None
    ordinal: int | None = None
    all: bool = False
```

### 8.4 多候选统一策略

这是硬规则：

```text
匹配 0 个：skipped，说明没有目标。
匹配 1 个：可以执行。
匹配多个 + 用户明确“全部/所有”：批量逐个 event_id 执行。
匹配多个 + 用户明确“第一个/第二个”：按 ordinal 执行。
匹配多个 + 用户没有明确范围：needs_clarification，绝不自动选择第一条。
```

### 8.5 query-first update/delete

对于：

```text
把 2026-05-18 的会议改到 10 点
删除 2026-05-18 的公司会议
```

必须：

```text
1. 先 query selector。
2. resolver 得到候选。
3. 0/1/N 按规则处理。
4. 只有 resolver 返回明确 event_id 列表，才进入 update/delete。
```

### 8.6 写后验证

update/delete/create 成功后，ResultVerifier 至少检查：

```text
update：被更新 event_id 是否是 resolver 选中的 event_id。
update：修改字段是否和用户请求一致。
delete：删除对象是否是 resolver 选中的 event_id。
create：新事件包含 date/start_time/title 等必要字段。
```

### 8.7 日历答案模板化

日历工具类答案优先模板化，不必交给 LLM。

查询结果只展示工具返回的：

```text
date
weekday_zh
time
title
location
```

如果工具没有 `weekday_zh`，最终答案不要自己算星期。

### 8.8 测试必须覆盖

```text
多候选 update 必须澄清
多候选 delete 必须澄清
明确“全部”才批量删除
明确“第一个/第二个”才能按 ordinal 执行
空查询后 delete skipped，不继续 delete multiple
指定真实 event_id update/delete 可执行
employee 写操作拒绝
日历 query 答案不自算星期
```

---

## 9. Milestone 4：AttendanceDomain 重构

### 9.1 目标

让考勤查询稳定，尤其是“异常”和“明细”语义。

### 9.2 建议新增模块

```text
src/mini_rag/capabilities/attendance/__init__.py
src/mini_rag/capabilities/attendance/models.py
src/mini_rag/capabilities/attendance/resolver.py
src/mini_rag/capabilities/attendance/formatter.py
```

### 9.3 统一规则

```text
异常 = late + leave + absent
异常不包含 present
明细 / 记录 / 员工名单 / 具体人员 => include_records=true
部门必须保真
日期范围必须绝对化
status_filters 必须是枚举列表
```

### 9.4 输出模板化

考勤统计类答案优先模板化，避免 LLM 编错数字。

### 9.5 测试必须覆盖

```text
异常统计包含 late/leave/absent
异常统计不包含 present
明细请求 include_records=true
部门筛选正确
日期范围正确
多状态查询正确
```

---

## 10. Milestone 5：RAG 能力保守治理，不大改

### 10.1 背景

当前 RAG 清洗后已经比较健康：hybrid_no_rerank 效果和延迟平衡较好。不要为了架构统一大改 RAG 主链路。

### 10.2 要做的事

1. 固化污染文件排除：

```text
RAG_EVAL_SEED_QUESTIONS.md
README*
MANIFEST*
DOCUMENT_MANIFEST*
VERIFY*
```

2. 保持默认：

```text
hybrid_no_rerank
```

3. RAG 评测主要看：

```text
Recall@K
Citation Hit Rate
Refusal Hit Rate
Groundedness
```

4. 工具答案不能伪造 RAG 引用。
5. 无证据时必须拒答。
6. RAG answer prompt 只接收 evidence，不接收完整 state。

### 10.3 测试

运行：

```bash
python scripts/agent_eval_suite_relaxed.py \
  --suite rag \
  --questions eval/rag_clean_eval_set/rag_clean_questions.jsonl \
  --judge rule \
  --mode hybrid \
  --output outputs/eval/rag_clean_hybrid
```

不得出现 RAG 指标明显回退。

---

## 11. Milestone 6：Answer Composer，防止工具做对但答案说错

### 11.1 目标

最终答案不能再重新推导确定性事实。

### 11.2 建议新增

```text
src/mini_rag/answer/__init__.py
src/mini_rag/answer/packet.py
src/mini_rag/answer/templates.py
src/mini_rag/answer/composer.py
```

### 11.3 三类答案策略

```text
Template Answer:
  datetime
  calendar query/write
  attendance query
  permission refusal
  clarification
  empty result

RAG Grounded Answer:
  企业知识库问答
  必须基于 retrieved evidence

Synthesis Answer:
  RAG + Tool 混合
  输入是 AnswerPacket，不是 raw state
```

### 11.4 禁止

Answer prompt 禁止：

```text
自己计算星期
自己推断写操作是否成功
自己推断权限
自己根据 raw JSON 编造日程
自己根据 tool_input 编造 tool_result
```

### 11.5 测试

```text
工具 query 成功，答案必须来自 tool_result/result_summary
工具 write skipped，答案不能说已完成
权限 refused，答案不能说已执行
日历无 weekday_zh，答案不输出星期
RAG answer 必须引用 sources
```

---

## 12. Milestone 7：Planner 降级，不再支配所有任务

### 12.1 目标

Planner 只处理复杂任务，不再默认被所有请求调用。

### 12.2 不是关键词 fast path

不要写：

```python
if "现在几点" in question: ...
```

正确做法：

```text
每个 capability 暴露 compile(ctx) -> CandidatePlan | None
Graph / Router 收集各 capability 编译结果
能确定性编译的走确定性计划
不能确定性编译且复杂度高的才调用 planner LLM
```

### 12.3 build_plan 的新职责

`build_plan` 只做：

```text
复杂任务拆解
多任务依赖
RAG + Tool 混合任务计划
上下文追问中的语义解析
```

`build_plan` 不做：

```text
权限最终判断
日期最终换算
event_id 最终选择
工具 schema 修复
多候选选择
答案生成
```

### 12.4 Planner 输出协议

只允许输出：

```json
{
  "execution_plan": {
    "tasks": []
  },
  "missing_required_slots": [],
  "reason": ""
}
```

不要输出重复分类字段：

```text
message_type
route
intent
selected_tool
selected_action
risk_level
time_requirement
knowledge_requirement
```

这些由上游 classification 或代码合并。

### 12.5 build_plan 输入裁剪

按 `selected_tool/selected_action` 裁剪工具契约：

```text
calendar query -> 只给 calendar query + datetime
calendar update -> 只给 calendar query/update + datetime
attendance query -> 只给 attendance query + datetime
rag -> 不给工具写操作契约
```

`context_usage=none` 时，不传 `previous_tool_context`。

### 12.6 验收测试

当前已有 `tests/test_planning_latency_contract.py` 可继续扩展。

必须覆盖：

```text
简单 datetime 任务不调用 build_plan
calendar query 的 build_plan prompt 不包含 update/delete/attendance
context_usage=none 时 build_plan prompt 不包含 previous_tool_context
build_plan 输出不复读分类字段
```

---

## 13. Milestone 8：工作流与 nodes.py 瘦身

### 13.1 目标

`nodes.py` 最终只保留 LangGraph 编排与兼容胶水，不承载领域业务。

### 13.2 迁移顺序

从 `nodes.py` 迁出：

```text
1. datetime / symbolic date 逻辑 -> datetime capability
2. calendar update/delete selector -> calendar capability
3. attendance status 清洗 -> attendance capability
4. tool input build/finalize -> capability validator / tool adapter
5. result formatter -> answer composer / capability formatter
6. prompt input裁剪 -> context policy
```

### 13.3 不要求一步到位

允许旧函数保留兼容 wrapper，但 wrapper 内只能调用新模块：

```python
def _resolve_calendar_delete_tasks(...):
    return calendar_domain.resolve_delete(...)
```

最终逐步删除 wrapper。

### 13.4 验收

`nodes.py` 中不应再出现大量：

```text
event_id=all/multiple 规则
present/late/leave/absent 清洗
today + 1 day 修复
calendar 多候选选择
answer formatter 大段业务模板
```

---

## 14. Milestone 9：最后才做性能优化

只有在能力正确性稳定后，再做：

```text
1. 减少不必要 LLM 调用。
2. 工具任务并行。
3. RAG 并行检索。
4. request-level TimeContext cache。
5. context pruning。
6. prompt token budget。
7. retrieval cache。
```

性能目标：

```text
datetime/direct：0 次 LLM，< 500ms
calendar/attendance query：0-1 次 LLM，< 2s
simple RAG：1 次 answer LLM，3-8s
mixed task：最多 1 次 planner LLM + 1 次 answer LLM，8-15s
```

但这些指标不能以牺牲正确性为代价。

---

## 15. 分阶段执行命令

每个 milestone 至少运行：

```bash
pytest -q
```

如果全量太慢，先运行相关测试，再全量：

```bash
pytest tests/test_agent_eval_suite_relaxed.py -q
pytest tests/test_daily_tools.py tests/test_planner_contract_validation.py -q
pytest tests/test_execution_plan_completion.py -q
pytest tests/test_langgraph_agent.py -q
```

评测建议：

```bash
# RAG 基线
python scripts/agent_eval_suite_relaxed.py \
  --suite rag \
  --questions eval/rag_clean_eval_set/rag_clean_questions.jsonl \
  --judge rule \
  --mode hybrid \
  --output outputs/eval/rag_clean_hybrid_after_refactor

# Tool 深度
python scripts/agent_eval_suite_relaxed.py \
  --suite tool \
  --questions eval/agent_eval_cases_v2_comprehensive/eval/tool_deep_eval_v2.jsonl \
  --judge rule \
  --output outputs/eval/tool_v2_after_refactor

# E2E 分批
python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --questions eval/agent_eval_cases_v2_comprehensive/eval/agent_e2e_comprehensive_v2.jsonl \
  --judge rule \
  --limit 20 \
  --output outputs/eval/e2e_v2_first20_after_refactor
```

---

## 16. 最终交付报告格式

Codex 完成每一阶段后，必须输出：

```text
## 本阶段目标

## 修改文件
- path: 做了什么

## 新增测试
- test_xxx: 验证什么

## 运行结果
- pytest ...
- eval ...

## 剩余风险

## 下一阶段建议
```

最终整体验收报告必须包含：

```text
1. Agent 能力矩阵通过率
2. RAG 指标是否退化
3. Tool / E2E actual_success
4. write_safety 结果
5. infra_error 是否单独统计
6. nodes.py 是否减少业务逻辑
7. LLM 调用次数与 prompt size 变化
```

---

## 17. 建议的第一批具体任务

请 Codex 从下面 3 个任务开始，不要先改性能链路：

### Task 1：评测脚本可信化

修改：

```text
scripts/agent_eval_suite_relaxed.py
tests/test_agent_eval_suite_relaxed.py
```

实现：

```text
infra_error 单独统计
默认 judge=rule
LLM judge 采样 / failed-only
fixture restore
日期/时间/星期/空结果归一化
```

### Task 2：日期硬门禁

修改：

```text
src/mini_rag/graph/time_contract.py
src/mini_rag/tools/input_contract.py
src/mini_rag/tools/datetime_tool.py
```

实现：

```text
TimeContext
last_week/this_week/next_week 自然周语义
工具入参 date/start_date/end_date 绝对化
禁止 symbolic date 进工具
```

### Task 3：Calendar write 安全门禁

修改：

```text
src/mini_rag/tools/calendar_resolution.py
src/mini_rag/graph/planning_contract.py
src/mini_rag/tools/input_contract.py
```

实现：

```text
缺槽 create/update/delete 不执行
多候选 update/delete 必须澄清
只有真实 EVT-... event_id 才能写入
employee 写操作拒绝
写后验证
```

这三步完成后，再进入 capability/domain 目录级拆分。

---

## 18. 核心判断

本项目下一阶段不是“追求 2 秒响应”，而是让 Agent 具备以下能力：

```text
知道自己能做什么；
知道什么时候不能做；
知道缺什么信息要问；
知道工具参数必须满足什么契约；
知道写操作必须先解析唯一对象；
知道工具结果与最终答案必须一致；
知道评测失败到底是哪一层错。
```

只有这些能力稳定了，再优化 LLM 调用次数和响应延迟。
