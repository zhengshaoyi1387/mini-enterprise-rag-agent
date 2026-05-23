# SQLite 企业工具 Adapter

本项目的 Agent 主链路保持不变：

`build_runtime_context -> plan_with_llm -> resolve_plan_time -> validate_plan -> react_execute -> answer_with_llm -> update_memory`

这次改动只把企业工具的数据源从本地 JSON/CSV mock 升级为轻量 SQLite adapter。Planner、Validator、ReActExecutor、Answer LLM、RAG Judge 都不需要知道数据库细节。

## 为什么接 SQLite

- 面试展示更像真实企业系统：日程、考勤、员工信息来自结构化数据库。
- 仍然轻量：使用 Python 标准库 `sqlite3`，不引入 SQLAlchemy 或微服务框架。
- 可替换：Repository 层可以替换成 HTTP/FastAPI/MCP adapter，工具返回契约不变。

## 数据库位置

默认数据库：

```bash
data/enterprise_demo.db
```

可通过环境变量覆盖：

```bash
ENTERPRISE_DB_PATH=data/enterprise_demo.db
```

## 表结构

核心 schema 在 [schema.sql](../src/mini_rag/infrastructure/db/schema.sql)。

- `employees`：员工基础信息，包含 `employee_id/name/department/role/manager/status`
- `calendar_events`：公司日程，包含 `event_id/title/event_date/start_time/end_time/location/event_type/department`
- `attendance_records`：考勤记录，包含 `employee_id/record_date/check_in/check_out/status/reason`
- `leave_records`：预留请假记录表

## 初始化 demo 数据

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/init_enterprise_db.py --reset
```

不想重置已有写入时：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/init_enterprise_db.py
```

种子数据覆盖：

- 2026-05-20 的两个日程：产品培训、项目复盘会
- 可用于 query-first update/delete 的固定 `EVT-...` event_id
- 2026-05-11 至 2026-05-17 的上周考勤异常与正常记录
- 员工、部门、角色基础数据

## Smoke Test

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python scripts/smoke_test_sqlite_tools.py
```

重点单测：

```bash
TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests/test_sqlite_tool_repositories.py -q
```

## 工具返回兼容性

`manage_company_calendar` 默认使用 SQLite。返回结构仍保留旧字段：

- query: `action/start_date/end_date/event_type/department/events`
- event: `event_id/date/time/title/type/department/location/description/weekday_zh`
- write: `status/message/event_id/event`

`query_attendance_summary` 默认使用 SQLite。返回结构仍保留旧字段：

- `start_date/end_date/filters/summary`
- `by_department` 或 `by_employee`
- `records`、`filtered_count`、`filtered_count_by_status`

只新增了兼容字段 `data_backend=sqlite|file`，用于 trace/debug。

## FastAPI Adapter 预留

新增内部 demo API：

- `GET /internal/calendar/events`
- `PATCH /internal/calendar/events/{event_id}`
- `GET /internal/attendance/records`

这些接口使用 `X-API-Key: <AGENT_API_KEY>` 保护。Agent 默认仍然直接调用 SQLite Repository，不强制绕 HTTP。

面试讲法：

> 当前本地 SQLite 模拟企业日程、考勤和员工系统。Agent 工具只依赖 Repository 接口和稳定返回契约；未来真实部署时，可以把 Repository 换成 FastAPI、HTTP、MCP Server 或企业内部系统 SDK，主链路和 Planner 都不用重写。

## 仍保留的兼容入口

为了不破坏现有测试和 fixture，工具仍支持显式传入 `file_path` 读取临时 JSON/CSV。默认生产/demo 路径已经是 SQLite；`file_path` 只作为测试 fixture 兼容层使用。
