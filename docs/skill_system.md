# Enterprise Skill Runtime

本项目现在仍然只有一条 Agentic RAG 主链路：

```text
build_runtime_context
-> plan_with_llm
-> resolve_plan_time
-> validate_plan
-> react_execute
-> answer_with_llm
-> update_memory
```

Skill Runtime 是这条主链路旁边的能力扩展机制，不替代 Planner、ReActExecutor、RAG Evidence Judge 或企业工具安全门禁。

## 为什么引入 Skill

一开始项目只有固定 Tool，例如日历查询、考勤查询、RAG 检索。固定 Tool 适合稳定 API，但不适合展示“企业能力可以被发现、按需加载、校验、执行和评测”的扩展方式。

Skill Runtime 解决的问题是：

- 能力不再只能写死在工具注册表里。
- Planner 不需要常驻读取长篇能力说明。
- 每个能力有 manifest、schema、entrypoint、限制和 eval cases。
- 执行过程有权限校验、schema 校验、timeout 和 trace。
- 后续可以把 Skill Manifest 映射到 MCP `tools/list`，把 SkillExecutor 映射到 MCP `tools/call`。

## Skill vs Tool

| 维度 | Tool | Skill |
| --- | --- | --- |
| 形态 | 固定 API 函数 | 能力包目录 |
| 描述 | 工具名、schema、action | manifest、Skill Card、SKILL.md、run.py、eval |
| 上下文 | 工具摘要进入 planner | 默认只暴露 Skill Card，完整 SKILL.md 按需加载 |
| 执行 | 进程内函数调用 | JSON stdin/stdout subprocess |
| 安全 | ToolExecutor/permission/schema | SkillExecutor 额外做权限、schema、timeout、cwd 限制 |
| 适合 | 日历/考勤/RAG 等基础能力 | 分析、证据检查、流程化 helper |

## Skill vs MCP

当前实现不是完整 MCP SDK。

- Skill 是本项目内部的能力包机制。
- MCP 是标准协议，更偏把工具、资源、上下文暴露给外部 Agent。
- 当前 Skill Manifest 可以后续映射成 MCP `tools/list`。
- 当前 SkillExecutor 可以后续映射成 MCP `tools/call`。

因此这是一条轻量、可面试展示的升级路径，而不是把项目拆成完整 MCP Server。

## Skill vs Rules / Instructions

Skill 不是新的关键词规则系统。

- `trigger_examples` 只用于轻量候选召回，不决定最终答案。
- `SKILL.md` 不常驻主 prompt，只有选中 Skill 后才加载。
- Skill 输出结构化 JSON，不直接篡改 Answer LLM 的事实来源。
- `policy_gap_checker` 可以做局部字符串覆盖分析，但不会把 candidate evidence 升级成 supporting evidence。

## Progressive Disclosure

Skill 有两层说明：

1. **Skill Card**：从 `skill.yaml` 生成，只包含名称、描述、风险、权限、触发样例、输入摘要。它适合放进 capability catalog。
2. **Skill Instruction**：`SKILL.md`，只有 Skill 被选中后由 `SkillLoader` 读取。

这样可以避免把所有 Skill 的完整说明长期塞进 Planner prompt。

## Manifest 字段

每个 Skill 位于 `skills/<skill_name>/`，至少包含：

- `skill.yaml`：元数据、schema、权限、依赖工具、eval cases。
- `SKILL.md`：适用场景、边界、输入输出解释、失败策略。
- `run.py`：通过 JSON stdin/stdout 执行。
- `eval_cases.json`：本 Skill 的 smoke/eval 样例。

核心字段：

- `name/version/description`
- `capability_type`
- `risk_level`: 当前只执行 `read_only`
- `required_permissions`
- `required_tools`
- `input_schema`
- `output_schema`
- `entrypoint`
- `timeout_seconds`

## SkillExecutor 安全

`SkillExecutor` 做这些事：

1. 从 `SkillRegistry` 找到 manifest。
2. 校验输入 JSON schema。
3. 检查 `required_permissions`。
4. 确认当前只执行 `read_only` skill。
5. 以 Skill 目录为 cwd 调用 `run.py`。
6. 通过 JSON stdin 传入参数。
7. 只传最小安全环境变量，不把 API Key 等敏感环境暴露给 Skill。
8. 捕获 stdout/stderr、timeout、非零退出码。
9. 校验输出 JSON schema。
10. 返回结构化 `ok/result/error/trace`。

## Trace 和 Eval

每次调用会记录：

- `selected`
- `input_validated`
- `permission_checked`
- `loaded`
- `executed`
- `output_validated`
- `failed`

失败不会直接抛到主流程，而是返回结构化错误，例如：

- `validation_error`
- `permission_denied`
- `timeout`
- `execution_error`
- `output_schema_error`

## 当前示例 Skill

### attendance_insight

用于做考勤洞察分析，不修改考勤记录，不回答制度原文。

它和 `query_attendance_summary` 的边界是：普通 Tool 负责查明细和基础统计，`attendance_insight` 负责在结构化考勤数据之上生成分析洞察。

能力：

- 按日期范围读取 SQLite `attendance_records`
- 支持 `group_by=employee/department/status`
- 统计 `late/leave/absent`
- 输出 `overview`、异常员工/部门排行、重复迟到、混合异常、部门集中异常等 `patterns`
- 输出 `risk_flags` 和 `suggested_followups`，用于 HR 周报或后续追问
- 保留旧版 `items` 字段，兼容原 AnswerPacket

### policy_gap_checker

用于分析 RAG evidence 是否覆盖问题槽位。

它不是 Evidence Judge，也不直接回答制度问题。它只基于传入的 evidence items 判断：

- 哪些 slot 已完整覆盖，`coverage_level=full`
- 哪些 slot 仅部分覆盖，`coverage_level=partial`
- 哪些 slot 缺失，`coverage_level=missing`
- overall 是 `full/partial/none`

它不会改变 Evidence Judge 的 `supporting_sources`，也不会把 `related_sources` 升级成可支撑最终结论的证据。

## 运行 Smoke Test

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/smoke_test_skills.py
```

重点单测：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests/test_enterprise_skill_runtime.py -q
```

## Agent 接入点

当前最小接入是新增固定 Tool：

```json
{
  "tool": "skill",
  "action": "run",
  "tool_input": {
    "skill_name": "attendance_insight",
    "arguments": {
      "start_date": "2026-05-11",
      "end_date": "2026-05-17"
    }
  }
}
```

`build_runtime_context` 会把 Skill Cards 放进 `capability_catalog.skill_cards`。Executor 真正调用 `skill.run` 时才加载对应 Skill 的 `SKILL.md` 和 `run.py`。

## 面试讲法

> 我项目里一开始只有固定工具，后来我加了一个轻量 Skill Runtime。普通 Tool 更像一个固定 API，而 Skill 是一个可发现、可按需加载的能力包，里面包含 manifest、输入输出 schema、执行脚本、说明文档、限制和 eval cases。Planner 默认只看到压缩后的 Skill Card，只有确定要用某个 Skill 时才加载 SKILL.md，这就是 progressive disclosure，可以避免 prompt 里长期塞太多工具细节。执行时 SkillExecutor 会做权限校验、schema 校验、timeout、结构化错误和 trace。后续如果要接 MCP，可以把 manifest 暴露成 tools/list，把 executor 暴露成 tools/call。

## 当前和完整 MCP 的差距

- 还没有实现 MCP transport/session。
- 还没有 MCP resources/prompts。
- Skill discovery 目前是本地目录扫描，不是远程 server capability negotiation。
- Skill 调用是 subprocess JSON，不是 MCP JSON-RPC。
- 当前只启用 read-only Skill。

后续升级方向：

1. 把 `SkillRegistry.list_skill_cards()` 暴露为 MCP `tools/list`。
2. 把 `SkillExecutor.execute()` 暴露为 MCP `tools/call`。
3. 为不同 Skill 增加更细粒度 sandbox 和审计策略。
4. 把 skill eval cases 接入现有 eval report。

