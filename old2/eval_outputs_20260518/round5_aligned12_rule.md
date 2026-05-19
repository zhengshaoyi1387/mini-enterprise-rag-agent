# Agent Evaluation Suite Report

- Generated at: `2026-05-17T12:10:56.931827+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 10 | 2 | 0.8333 | 14988.25 | 22602.91 |
| e2e | 12 | 10 | 2 | 0.8333 | 14988.25 | 22602.91 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 12 |
| executed_cases | 12 |
| infra_error_cases | 0 |
| agent_passed_cases | 10 |
| agent_failed_cases | 2 |
| agent_pass_rate | 0.8333 |
| case_count | 12 |
| passed | 10 |
| failed | 2 |
| pass_rate | 0.8333 |
| avg_latency_ms | 14988.25 |
| p95_latency_ms | 22602.91 |
| actual_success_no_blocked_tasks | 1.0 |
| answer_must_contain_hit | 0.9167 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 1.0 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 1.0 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 0.8333 |
| task_success | 0.8333 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_tool_004

- Question: 统计 2026 年 5 月迟到员工明细，并告诉我产品部本月有哪些异常。
- Failure reasons: task_success, refusal_accuracy, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "query_attendance_summary", "action": "query", "args": {"start_date": "2026-05-01", "end_date": "2026-05-31", "department": "all", "group_by": "employee", "status_filter": "late", "include_records": true, "query": "统计 2026 年 5 月迟到员工明细，并告诉我产品部本月有哪些异常。", "user_id": "eval_user", "role": "hr"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "query_attendance_summary", "action": "query", "args": {"start_date": "2024-06-01", "end_date": "2024-06-30", "department": "产品部", "group_by": "employee", "status_filters": ["late", "leave", "absent"], "include_records": true, "query": "统计 2026 年 5 月迟到员工明细，并告诉我产品部本月有哪些异常。", "user_id": "eval_user", "role": "hr"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "统计 2026 年 5 月迟到员工明细", "status": "ok", "tool_name": "query_attendance_summary", "action": "query", "tool_input": {"start_date": "2026-05-01", "end_date": "2026-05-31", "department": "all", "group_by": "employee", "status_filter": "late", "include_records": true}, "result_summary": "2026-05-01 至 2026-05-31 共有 12 条迟到记录：李四（研发部，打卡 09:35）；周八（产品部，打卡 09:28）；李四（研发部，打卡 09:31）；孙七（产品部，打卡 09:26）；赵六（HR，打卡 09:22）；张三（研发部，打卡 09:29）；王五（销售部，打卡 09:34）；周八（产品部，打卡 09:27）；孙七（产品部，打卡 09:33）；王五（销售部，打卡 09:25）；赵六（HR，打卡 09:32）；孙七（产品部，打卡 09:21）。", "tool_result": {"filtered_count": 12, "records": [{"date": "2026-05-01", "employee_id": "u002", "name": "李四", "department": "研发部", "status": "late", "check_in": "09:35", "check_out": "18:05"}, {"date": "2026-05-01", "employee_id": "u006", "name": "周八", "department": "产品部", "status": "late", "check_in": "09:28", "check_out": "18:02"}, {"date": "2026-05-04", "employee_id": "u002", "name": "李四", "department": "研发部", "status": "late", "check_in": "09:31", "check_out": "18:00"}, {"date": "2026-05-05", "employee_id": "u005", "name": "孙七", "department": "产品部", "status": "late", "check_in": "09:26", "check_out": "18:30"}, {"date": "2026-05-07", "employee_id": "u004", "name": "赵六", "department": "HR", "status": "late", "check_in": "09:22", "check_out": "18:06"}, {"date": "2026-05-08", "employee_id": "u001", "name": "张三", "department": "研发部", "status": "late", "check_in": "09:29", "check_out": "18:12"}, {"date": "2026-05-08", "employee_id": "u003", "name": "王五", "department": "销售部", "status": "late", "check_in": "09:34", "`
- Answer preview: 根据工具查询结果，分两部分回答您的问题：

---

### 一、2026 年 5 月迟到员工明细

2026 年 5 月 1 日至 5 月 31 日期间，共有 **12 条迟到记录**，涉及以下员工：

- **李四**（研发部）：5 月 1 日（09:35）、5 月 4 日（09:31）  
- **周八**（产品部）：5 月 1 日（09:28）、5 月 11 日（09:27）  
- **孙七**（产品部）：5 月 5 日（09:26）、5 月 12 日（09:33）、5 月 16 日（09:21）  
- **赵六**（HR）：5 月 7 日（09:22）、5 月 15 日（09:32）  
- **张三**（研发部）：5 月 8 日（09:29）  
- **王五**（销售部）：5 月 8 日（09:34）、5 月 14 日（09:25）

---

### 二、产品部本月异常考勤情况

您询问的是“产品部本月有哪些异常”，但第二项任务查询的是 **2024 年 6 月**（而非 2026 年 5 月）的产品部异常考勤（迟到/请假/缺勤），结果显示该时间段内 **无任何异常记录**。

> ⚠️ 注意：由于第二项任务的时间范围为 2024 年 6 月，与第一项任务的 2026 年 5 月不一致，**无法提供产品部在 2026 年 5 月的完整异常考勤汇总**（如请假、缺勤等）。  
> 不过，从第一项任务的迟到明细中可知，产品部在 2026 年 5 月有 **2 名员工迟到**：  
> - **周八**：迟到 2 次  
> - **孙七**：迟到 3 次  

若需产品部在 **2026 年 5 月** 的完整异常（含请假、缺勤）数据，请重新发起针对该时间段和部门的查询。

### e2e / e2e_tool_011

- Question: 把那个会议改成 10 点。
- Failure reasons: task_success, answer_must_contain_hit, refusal_accuracy, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 我还缺少必要信息：event_id。请补充后我再继续处理。
