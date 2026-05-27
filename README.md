# Mini Enterprise Agentic RAG

一个面向企业问答场景的 Agentic RAG 示例项目，支持企业知识库检索、结构化工具调用、日历/考勤数据查询、受控写操作、Skill 扩展和执行 trace。项目使用 FastAPI 提供接口，Agent 主流程基于 LangGraph 风格的状态链路组织。

## 功能概览

- 企业知识库问答：支持多知识库检索和基于证据的回答。
- 结构化工具调用：支持公司日历、考勤等企业工具。
- 日历写操作：支持创建、更新、删除日程，并带有权限校验和安全校验。
- Skill Runtime：支持按需调用企业 Skill，例如考勤异常分析和 RAG 证据缺口检查。
- 可观测性：保留 planner、tool call、RAG evidence、answer packet 等 trace，方便调试和评测。

## 环境准备

建议使用 Python 3.10+。

```bash
pip install -e .
```

如果你使用独立虚拟环境，可以先创建并激活环境：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\\Scripts\\activate
pip install -e .
```

## 初始化示例数据

项目默认使用本地 SQLite 作为企业工具数据源。首次运行前可以初始化 demo 数据：

```bash
TMPDIR=/tmp PYTHONPATH=src python scripts/init_enterprise_db.py --reset
```

初始化后会生成或重置：

```text
data/enterprise_demo.db
```

## 启动服务

```bash
PYTHONPATH=src uvicorn mini_rag.api.app:app --reload
```

服务默认启动在：

```text
http://127.0.0.1:8000
```

## 调用接口

主要问答接口：

```text
POST /chat
POST /chat/stream
```

示例请求：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "我明天有会议吗？",
    "session_id": "demo"
  }'
```

流式接口可用于前端逐步展示回答：

```bash
curl -X POST http://127.0.0.1:8000/chat/stream \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "介绍一下公司的报销制度",
    "session_id": "demo"
  }'
```

## CLI 使用

也可以直接通过命令行测试 Agent：

```bash
PYTHONPATH=src python -m mini_rag.cli ask "我明天有会议吗？"
```

或：

```bash
PYTHONPATH=src python scripts/ask.py "查一下产品部上周考勤异常"
```

## 常用测试命令

编译检查：

```bash
TMPDIR=/tmp PYTHONPATH=src python -m compileall -q src tests
```

运行测试：

```bash
TMPDIR=/tmp PYTHONPATH=src python -m pytest tests -q
```

SQLite 工具 smoke test：

```bash
TMPDIR=/tmp PYTHONPATH=src python scripts/smoke_test_sqlite_tools.py
```

Skill smoke test：

```bash
TMPDIR=/tmp PYTHONPATH=src python scripts/smoke_test_skills.py
```

运行一组 Agent 评测：

```bash
TMPDIR=/tmp PYTHONPATH=src python scripts/agent_eval_suite_relaxed.py \
  --suite e2e \
  --judge rule \
  --questions eval/agent_eval_cases_full/agent_e2e_eval_cases_aligned.jsonl \
  --output outputs/eval/aligned12_rule
```

## 项目结构

```text
src/mini_rag/
  agent/              # Agent 统一入口
  api/                # FastAPI 接口
  graph/              # Workflow 状态与提示词
  orchestration/      # Planner、Validator、Executor、Completion
  capabilities/       # datetime、calendar、attendance、rag 等领域能力
  execution/          # 工具输入构造与执行保护
  answer/             # AnswerPacket 与最终回答生成
  skills/             # Skill Runtime
  tools/              # 企业工具实现
  infrastructure/db/  # SQLite repository 和 demo 数据
```

## 典型问题示例

```text
介绍一下公司的报销制度
我明天有会议吗？
把下周日的公司会议地点改成 2号会议室
新建一个会议，时间5月28日早上八点到九点，地点会议室B，会议为动员大会
查一下产品部上周考勤异常
帮我分析上周考勤异常里有没有值得 HR 关注的风险员工
```

## 说明

本项目侧重展示 Agentic RAG 在企业场景下的工程链路：问题理解、计划生成、时间解析、权限与 schema 校验、工具/RAG/Skill 执行、结果校验和最终回答约束。示例数据使用本地 SQLite，真实业务接入时可以替换为内部 API、数据库服务或 MCP 工具服务。
