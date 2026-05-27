# Mini Enterprise Agentic RAG

这个项目只保留一条 Agentic RAG 主线，用于企业知识库问答、结构化日历/考勤工具调用、受控 RAG 检索和可追踪评测。

## 唯一请求入口

所有问答都走 Agentic 主线：

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

旧普通 RAG chain、匿名兼容问答入口和规则式工具选择已经移除。服务入口只保留 `/chat` 和 `/chat/stream`，健康检查、鉴权、管理和评测接口仍按 FastAPI 网关职责保留。

## 唯一 RAG 子链路

RAG 不再有独立普通分支。它只作为 ReAct 执行器中的一种 action 运行：

```text
ReActExecutor.search_rag
-> RAGRetrievalService.retrieve
-> retrieve
-> LLM Evidence Judge
-> evidence insufficient 时 RAG Reflect
-> retry retrieve
-> LLM Evidence Judge
-> supporting_sources 进入最终回答
-> candidate_sources 只进 trace/debug
```

`RagAnswerabilityGate` 只做结构检查：RAG task 必须有 LLM Evidence Judge 认可的 `supporting_sources` 才可回答。`candidate_sources` 不会进入最终 Answer LLM prompt。

## 运行

```bash
pip install -e .
uvicorn mini_rag.api.app:app --reload
```

登录后调用 `/chat`：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"介绍一下公司的报销制度","session_id":"demo"}'
```

CLI 也走同一条 Agentic 主线：

```bash
python -m mini_rag.cli ask "我明天有会议吗？如果有，出差报销回来要注意什么？"
python scripts/ask.py "查一下产品部上周考勤异常，再结合考勤制度说明常见处理方式。"
```

## 核心目录

```text
src/mini_rag/
  agent/                 # EnterpriseKnowledgeAgent 统一入口
  api/                   # FastAPI /chat, /chat/stream, auth/admin/eval
  graph/                 # workflow/state；nodes.py 仅暴露当前 runtime 类
  orchestration/         # AgenticRAGNodes, ReActExecutor, state views
  capabilities/          # datetime/calendar/attendance/rag 领域能力
  execution/             # tool executor 和 tool input guardrails
  answer/                # AnswerPacket 与 Answer LLM
  memory/                # 会话记忆更新
  observability/         # trace builder/report
  skills/                # Enterprise Skill Runtime：manifest/card/loader/executor
  tools/                 # 真实结构化工具
  infrastructure/db/     # SQLite schema/seed，本地模拟企业系统
```

## Enterprise Skill Runtime

项目新增轻量 Skill Runtime，但不改变 Agent 主链路。Skill 是可发现、可按需加载、可校验、可执行、可观测的企业能力包：

```text
skills/<skill_name>/
  skill.yaml      # manifest: 元数据、schema、权限、entrypoint、eval cases
  SKILL.md        # 只有选中 skill 后才加载的详细说明
  run.py          # JSON stdin/stdout 执行入口
  eval_cases.json # skill smoke/eval 样例
```

当前示例：

- `attendance_insight`：基于 SQLite 考勤数据统计迟到、请假、缺勤等异常分布。
- `policy_gap_checker`：检查 RAG evidence 是否覆盖用户问题关键槽位，不替代 Evidence Judge。

最小 Agent 接入是固定工具 `skill.run`。`build_runtime_context` 会把压缩后的 Skill Cards 放入 `capability_catalog.skill_cards`，真正执行时才加载完整 `SKILL.md` 和 `run.py`，避免把所有 Skill 文档常驻 Planner prompt。

Skill smoke test：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/smoke_test_skills.py
```


## SQLite 企业工具数据源

`manage_company_calendar` 和 `query_attendance_summary` 默认读取 `data/enterprise_demo.db`，不再依赖硬编码内存数据。SQLite 使用标准库 `sqlite3`，通过 repository 层隔离数据访问，工具返回字段保持兼容。

初始化 demo 数据：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/init_enterprise_db.py --reset
```

工具 smoke test：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/smoke_test_sqlite_tools.py
```

内部 adapter 预留了轻量 FastAPI 接口：`GET /internal/calendar/events`、`PATCH /internal/calendar/events/{event_id}`、`GET /internal/attendance/records`。Agent 默认仍直接调用 SQLite repository；真实部署时可把 repository 换成 FastAPI/HTTP/MCP，而不改主链路。更多说明见 [docs/sqlite_tools.md](docs/sqlite_tools.md)。

## 安全边界

- 时间解析由 `capabilities/datetime/resolver.py` 统一完成，工具不消费 `今天/明天/下周` 等 symbolic date。
- Calendar 写操作必须通过 validator/resolver，不能让 `event_id=all/multiple/*` 进入真实工具。
- 多候选 update/delete 默认澄清，只有明确 selector 或真实 `EVT-...` 才执行。
- Answer LLM 只能基于 `AnswerPacket` 中的 resolved time facts、tool results、supporting RAG evidence、safety/permission events 回答。
- RAG 的候选证据只用于 trace/debug，最终回答只使用 LLM Judge 认可的 supporting evidence。

## 测试与评测



```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m compileall -q src tests
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests -q
```

评测脚本仍保留 `rag/tool/e2e` suite 名称，但 RAG suite 也通过 `EnterpriseKnowledgeAgent` 执行，不再绕过 Agentic 主线：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --judge rule \
  --questions eval/agent_eval_cases_full/agent_e2e_eval_cases_aligned.jsonl \
  --output outputs/eval/aligned12_rule
```
