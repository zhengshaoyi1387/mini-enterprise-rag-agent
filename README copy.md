# Mini Enterprise Agentic RAG

一个面向企业内部知识问答、结构化工具调用、受控 ReAct、Skill Runtime 和可观测评测的工程化 Agentic RAG 项目。

本项目不是“检索文档后直接让大模型回答”的课程 Demo，而是把企业 Agent 拆成一条稳定、可校验、可追踪的主链路：先构建运行上下文，再由 Planner 生成任务与目标，统一解析时间，做权限和安全校验，执行 RAG / Tool / Skill，最后只基于真实事实生成回答。

---

## 1. 项目定位

Mini Enterprise Agentic RAG 模拟企业内部智能助手，支持三类典型任务：

1. **企业知识库问答**
   - 报销制度、考勤制度、IT 安全规范、产品文档、FAQ 等。
   - 支持按用户角色过滤可访问知识库。
   - 通过 Evidence Judge 判断证据是否足够，避免 RAG 幻觉。

2. **结构化工具调用**
   - 查询当前日期时间。
   - 查询、创建、修改、删除公司日程。
   - 查询考勤明细、异常统计和汇总。
   - 工具接入 SQLite 企业数据源，保留 FastAPI / MCP 替换空间。

3. **企业 Skill 分析能力**
   - `attendance_insight`：基于考勤数据做异常分析、风险员工识别、统计洞察。
   - `policy_gap_checker`：对 RAG evidence 做证据覆盖缺口检查，不替代 Evidence Judge。

项目目标是展示一个企业 Agent 的完整工程闭环：

- 主链路清晰，不靠一堆分散 if/else。
- 工具调用有权限、schema、event_id、安全校验。
- RAG 有证据分层、Reflect retry 和 partial answer。
- Calendar 写操作有 query-then-update、澄清、确认和真实结果验收。
- Answer 只能基于 AnswerPacket 中的真实事实，不能编造成功或引用。
- Trace、mainline_log、LLM IO、评测和 smoke test 支持定位问题。

---

## 2. 唯一主链路

所有请求统一走 Agentic 主线：

```text
/chat 或 /chat/stream
-> EnterpriseKnowledgeAgent
-> EnterpriseKnowledgeGraphAgent
-> AgenticRAGWorkflow
-> build_runtime_context
-> plan_with_llm
-> resolve_plan_time
-> validate_plan
-> react_execute
-> answer_with_llm
-> update_memory
```

各节点职责：

| 节点 | 职责 |
|---|---|
| `build_runtime_context` | 构建用户身份、角色、权限、可访问 KB、工具能力、Skill Card、当前时间、历史上下文 |
| `plan_with_llm` | 生成 execution_plan 和 goal_contract；只做语义理解和任务规划，不计算日期 |
| `resolve_plan_time` | 统一解析“明天、下周日、上周”等相对时间，生成绝对日期或日期范围 |
| `validate_plan` | 校验权限、schema、风险等级、event_id、安全边界，拦截危险写操作 |
| `react_execute` | 执行 RAG / Tool / Skill；根据 observation 做受控状态转移 |
| `answer_with_llm` | 基于 AnswerPacket 生成最终回答，受 completion_check 和 evidence gate 约束 |
| `update_memory` | 写入会话记忆，支持 follow-up 和 previous_tool_context |

旧的普通 RAG chain、规则式工具选择和绕过主链路的问答入口已收口，服务入口主要保留 `/chat` 与 `/chat/stream`。

---

## 3. 核心设计亮点

### 3.1 Time Contract：时间单入口

时间处理是本项目重点收口的地方。Planner 不允许自己计算日期，也不允许把多个时间字段散落在不同位置。

最终约定：

```text
Planner 可以输出 task.time_expression / task.date_expression / tool_input.date_expression / pending_update.date_expression
Normalizer 统一收敛为 task.time_expression
TimeResolver 只消费 task.time_expression
工具调用前移除 date_expression，只传 start_date / end_date / date
Answer 只能使用 resolved_time_facts 或工具返回的日期与星期
```

这样可以避免：

- Planner 自己算错日期。
- `task.time_expression=下周日` 和 `tool_input.date_expression=下个星期日` 被拆成两个 query。
- objective 里的“当前信息”被误识别为时间。
- Answer LLM 自己推算星期。

### 3.2 Calendar Update Contract：target 和 expected_result 分离

Calendar 写操作采用明确协议：

```json
{
  "goal_type": "calendar_update",
  "target": {
    "title": "OKR 年中复盘会",
    "date_expression": "下周日",
    "event_type": "meeting"
  },
  "expected_result": {
    "time": "20:00-21:00"
  }
}
```

含义：

- `target`：用来定位要修改的事件。
- `expected_result`：只放用户明确要修改成什么。

例如“把 OKR 年中复盘会改到晚上八点到九点”，`OKR 年中复盘会` 是 target，不是要修改后的 title；`20:00-21:00` 才是 expected_result。

### 3.3 受控 ReAct / Goal-aware Executor

本项目不是完全自由的 ReAct，不让 LLM 每一步随意决定新工具调用。项目采用企业场景更安全的 **Controlled ReAct / Goal-aware Execution**：

```text
Goal Contract
-> Initial Plan
-> Tool Observation
-> Safe State Transition
-> Completion Check
-> Answer Gate
```

Calendar 写操作的状态转移：

```text
query 0 个候选 -> not_found，不执行写操作
query 1 个候选 -> 注入真实 event_id，执行 update
query 多个候选 -> needs_clarification，不擅自写
用户选择多个候选 -> 进入二次确认
用户确认 -> 拆成多个单 event_id update
```

关键原则：

- 任务执行完不等于用户目标完成。
- 必须用 `completion_check` 验收目标是否达成。
- 只有真实 `tool_result.status=updated/created/deleted` 且字段匹配 expected_result，Answer 才能说成功。
- `event_id=all/*/multiple/placeholder` 不能进入真实写工具。

### 3.4 Duplicate Guardrail：读写分离

重复操作的处理遵循读写风险分级：

```text
duplicate query -> 复用 observation / no-op，不阻断后续 update
duplicate create/update/delete -> 拦截，避免重复写入
```

这避免了“重复查询被 guardrail block，导致后续 update 不执行”的问题，同时保留写操作安全边界。

### 3.5 Answer Gate：禁止 false success

Answer LLM 只能基于 AnswerPacket 回答。对于日历写操作，必须同时满足：

```text
completion_check.status = completed
真实 tool_result.status in [created, updated, deleted]
返回事件字段与 expected_result 匹配
```

否则只能回答：

- 未找到目标会议。
- 匹配到多个候选，需要澄清。
- 工具失败或执行未完成。

`write_not_executed` 只用于禁止误报成功，不覆盖具体的 not_found / needs_clarification / failed 说明。

---

## 4. RAG 可靠性设计

RAG 不是简单 top-k 拼 prompt，而是：

```text
retrieve candidates
-> LLM Evidence Judge
-> supporting_sources / related_sources / unsupported 分层
-> evidence insufficient 时触发 Reflect retry
-> retry retrieve
-> 再次 Evidence Judge
-> Answer 只使用 supporting_sources
```

### Evidence 类型

| 类型 | 作用 |
|---|---|
| `supporting_sources` | Judge 认可、可以支撑最终答案的证据 |
| `related_sources` | 相关但不足以完整回答，只能作为相关参考 |
| `candidate_sources` | 原始候选，只进 trace/debug，不直接进入最终回答 |

### Mixed Partial Answerability

多子任务问题不做全局一票否决：

```text
全部 supported -> full answer
部分 supported -> partial answer
全部 unsupported -> no evidence answer
unsupported + related -> related reference answer
```

例如：用户同时问“考勤制度编号”和“酒店费报销流程”，如果只有考勤制度有证据，系统会回答有证据的部分，并说明酒店费报销在当前知识库中没有明确依据。

### policy_gap_checker 边界

`policy_gap_checker` 只做证据缺口分析：

- 不直接回答制度问题。
- 不替代 Evidence Judge。
- 不把 related_sources 升级成 supporting_sources。

---

## 5. Enterprise Skill Runtime

Skill Runtime 是项目从固定工具走向可扩展能力包的核心亮点。

Skill 目录结构：

```text
skills/<skill_name>/
  skill.yaml       # manifest: 元数据、schema、权限、entrypoint、eval cases
  SKILL.md         # 只有选中后才加载的详细说明
  run.py           # JSON stdin/stdout 执行入口
  eval_cases.json  # skill smoke/eval 样例
```

已实现 Skill：

| Skill | 用途 | 边界 |
|---|---|---|
| `attendance_insight` | 考勤异常统计、排行、风险分析、HR 关注建议 | 不查原始明细，明细仍走 `query_attendance_summary` |
| `policy_gap_checker` | 检查 RAG evidence 是否覆盖问题关键槽位 | 不替代 Evidence Judge，不直接生成制度结论 |

Skill Runtime 特点：

- Planner 默认只看压缩后的 Skill Card。
- 只有选中某个 Skill 后才加载完整 `SKILL.md`。
- Executor 通过 JSON stdin/stdout 调用 `run.py`。
- 执行前做 input schema、权限、timeout、cwd 校验。
- 执行后做 output schema、stdout/stderr、trace 记录。

和 MCP 的关系：

```text
Skill manifest 可映射为 MCP tools/list
Skill executor 可映射为 MCP tools/call
```

当前项目没有做完整 MCP Server，而是实现了一个轻量可解释的 Skill Runtime，为后续 MCP 化留接口。

---

## 6. SQLite / FastAPI 工具数据源

`manage_company_calendar` 和 `query_attendance_summary` 默认读取：

```text
data/enterprise_demo.db
```

特点：

- 使用标准库 `sqlite3`。
- 通过 repository 层隔离数据访问。
- 工具 schema 与 Agent 主链路解耦。
- 预留 FastAPI 内部接口和 MCP 替换空间。

初始化 demo 数据：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/init_enterprise_db.py --reset
```

工具 smoke test：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/smoke_test_sqlite_tools.py
```

更多说明见：

```text
docs/sqlite_tools.md
docs/skill_system.md
```

---

## 7. 典型测试问题

### Calendar 写安全

```text
把 OKR 年中复盘会改到晚上八点到九点。
```

期望：query 唯一目标，update 成功，completion_check completed。

```text
把明天的公司会议改到晚上九点。
```

期望：0 候选，不 update，回答未找到目标会议。

```text
把下周的公司会议改到早上九点到十点。
```

期望：多候选，不擅自更新，要求澄清。

```text
两个都改。
确认。
```

期望：先二次确认，再拆成多个真实 event_id update。

```text
把下周日的公司会议地点改成 2号会议室。
```

期望：query 唯一候选，注入真实 event_id，update location。

### Skill 边界

```text
查一下上周有哪些员工存在考勤异常，给我明细。
```

期望：走 `query_attendance_summary`，不走 `attendance_insight`。

```text
帮我分析上周考勤异常里有没有值得 HR 关注的风险员工。
```

期望：走 `skill.run -> attendance_insight`。

### RAG partial answer

```text
考勤与休假管理制度的文档编号是多少？出差的酒店费能不能报销？如果能，流程是什么？
```

期望：有证据的部分回答；酒店费如果没有 supporting evidence，不强答，不伪造引用。

---

## 8. 运行方式

安装：

```bash
pip install -e .
```

启动 API：

```bash
uvicorn mini_rag.api.app:app --reload
```

调用 `/chat`：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"介绍一下公司的报销制度","session_id":"demo"}'
```

CLI：

```bash
python -m mini_rag.cli ask "我明天有会议吗？如果有，出差报销回来要注意什么？"
python scripts/ask.py "查一下产品部上周考勤异常，再结合考勤制度说明常见处理方式。"
```

---

## 9. 测试与评测

推荐命令：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m compileall -q src tests scripts skills

TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/smoke_test_skills.py

TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests/test_unified_mainline_safety.py -q

TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests/test_daily_tools.py tests/test_enterprise_extensions.py -q
```

如果环境依赖完整，可以跑：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest -q
```

评测脚本：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --judge rule \
  --questions eval/agent_eval_cases_full/agent_e2e_eval_cases_aligned.jsonl \
  --output outputs/eval/aligned12_rule
```

---

## 10. 核心目录

```text
src/mini_rag/
  agent/                 # EnterpriseKnowledgeAgent 统一入口
  api/                   # FastAPI /chat, /chat/stream, auth/admin/eval
  graph/                 # workflow/state；nodes.py 只保留当前 runtime facade
  orchestration/         # AgenticRAGNodes, ReActExecutor, completion, protocol normalizer
  capabilities/          # datetime/calendar/attendance/rag 领域能力
  execution/             # tool executor 和 tool input guardrails
  answer/                # AnswerPacket 与 Answer LLM
  memory/                # 会话记忆更新
  observability/         # trace builder/report
  skills/                # Enterprise Skill Runtime
  tools/                 # 真实结构化工具
  infrastructure/db/     # SQLite schema/seed，本地模拟企业系统
```

---

## 11. 当前边界与后续方向

当前已经完成：

- 单一 Agentic 主链路。
- RAG Evidence Judge + Reflect retry。
- Tool / RAG / Skill 混合执行。
- Calendar query-then-update 安全闭环。
- Goal-aware completion_check。
- Skill Runtime。
- SQLite 企业工具数据源。
- AnswerPacket 防幻觉和 false success。
- Trace / mainline_log / LLM IO。

当前刻意不做：

- 不做完全自由的通用 ReAct。
- 不让 LLM 每一步自由生成写操作。
- 不做复杂多 Agent。
- 不做完整 MCP Server，只保留 Skill Runtime 和后续映射空间。
- 不继续堆自然语言关键词规则。

后续可选增强：

- 把 controlled recovery policy 写成更系统的状态机。
- 为 calendar 最新闭环补充更多 pytest 回归。
- 把 Skill manifest 映射到极简 MCP tools/list 和 tools/call。
- 接真实企业系统 API 替代 SQLite repository。

---

## 12. 一句话面试定位

这个项目的核心不是“我做了一个 RAG Demo”，而是：

> 我把企业内部问答、结构化工具调用、受控 ReAct、RAG 证据判断、Skill Runtime、权限安全和可观测评测收敛成了一条稳定的 Agentic Workflow。系统不是任务跑完就说成功，而是通过 goal_contract 和 completion_check 验收用户目标是否真的完成；RAG 不是检索到就回答，而是经过 Evidence Judge 和 Reflect；工具写操作不是 LLM 自由发挥，而是通过 query-then-update、event_id 绑定、多候选澄清和二次确认来保证安全。
