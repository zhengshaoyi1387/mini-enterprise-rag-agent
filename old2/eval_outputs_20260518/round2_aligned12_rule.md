# Agent Evaluation Suite Report

- Generated at: `2026-05-17T11:44:11.296169+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 10 | 2 | 0.8333 | 17455.90 | 30281.22 |
| e2e | 12 | 10 | 2 | 0.8333 | 17455.90 | 30281.22 |

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
| avg_latency_ms | 17455.9 |
| p95_latency_ms | 30281.22 |
| actual_success_no_blocked_tasks | 0.9167 |
| answer_must_contain_hit | 0.9167 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_tool_coverage | 0.9167 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 0.9167 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 1.0 |
| task_success | 0.8333 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_tool_001

- Question: 先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。
- Failure reasons: task_success, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "type_filtered", "event_type": "activity", "department": "all", "query": "先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "manage_company_calendar", "action": "update", "args": {"action": "update", "event_id": "EVT-20260519-0001", "title": "公司高层会议", "type": "meeting", "date": "", "time": "21:00-22:00", "location": "会议室A", "query": "先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。", "user_id": "eval_user", "role": "admin"}, "ok": false, "error": "invalid date format", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询下周所有公司团建日程", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "type_filtered", "event_type": "activity", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-24 的公司日程：\n- 2026-05-19 星期二 16:00-18:00 公司团建（城市公园，event_id：EVT-20260519-0001）\n- 2026-05-21 星期四 18:00-20:00 公司团建（团建餐厅，event_id：EVT-20260521-0002）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260519-0001", "date": "2026-05-19", "title": "公司团建", "type": "activity", "department": "all", "time": "16:00-18:00", "location": "城市公园", "description": "下周第一个团建活动，用于 update/delete 评测", "weekday_zh": "星期二"}, {"event_id": "EVT-20260521-0002", "date": "2026-05-21", "title": "公司团建", "type": "activity", "department": "all", "time": "18:00-20:00", "location": "团建餐厅", "description": "第二个团建活动", "weekday_zh": "星期四"}]}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "将查询结果中的第一条团建日程更新为公司高层会议，时间21:00-22:00，地点会议室A", "status": "error", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "event_id": "EVT-20260519-0001", "title": "公司高层会议", "type": "meeting", "date": "", "time": "21:00-22:00", "location": "会议室A"}, "result_summary": "工具调用失败：invalid date format", "tool_result": {"error": "invalid date format"}, "source_count": 0, "error_message": "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"}]`
- Answer preview: ### 1. 查询下周所有公司团建日程  
根据工具查询结果，2026-05-18 至 2026-05-24 期间的公司团建日程如下：  
- **2026-05-19 星期二 16:00–18:00**：公司团建（城市公园，event_id：EVT-20260519-0001）  
- **2026-05-21 星期四 18:00–20:00**：公司团建（团建餐厅，event_id：EVT-20260521-0002）  

### 2. 尝试更新第一个团建日程  
已尝试将第一条日程（event_id：EVT-20260519-0001）更新为“公司高层会议”，时间 21:00–22:00，地点会议室A，但工具调用失败，原因为 **“invalid date format”**（日期格式无效）。  

由于缺少有效的日期字段或格式不正确，该更新操作未能完成。如需继续，请提供符合要求的完整日期信息。

### e2e / e2e_tool_008

- Question: 现在的日期时间是多少？顺便查一下明天的公司会议安排。
- Failure reasons: task_success, expected_tool_coverage, answer_must_contain_hit, multi_task_completion_rate, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai", "query": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "获取当前日期和时间", "status": "ok", "tool_name": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}, "result_summary": "当前日期：2026-05-17，时间：19:43:12，星期：Sunday，时区：Asia/Shanghai。", "tool_result": {"current_time": "19:43:12", "current_date": "2026-05-17", "timezone": "Asia/Shanghai", "weekday_zh": "星期日", "ranges": {"today": {"start_date": "2026-05-17", "end_date": "2026-05-17"}, "yesterday": {"start_date": "2026-05-16", "end_date": "2026-05-16"}, "tomorrow": {"start_date": "2026-05-18", "end_date": "2026-05-18"}, "day_after_tomorrow": {"start_date": "2026-05-19", "end_date": "2026-05-19"}, "this_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"}, "last_week": {"start_date": "2026-05-04", "end_date": "2026-05-10"}, "next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}, "week_after_next": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "next_next_week": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "this_month": {"start_date": "2026-05-01", "end_date": "2026-05-31"}, "last_month": {"start_date": "2026-04-01", "end_date": "2026-04-30"}, "next_month": {"start_date": "2026-06-01", "end_date": "2026-06-30"}, "month_after_next": {"start_date": "2026-07-01", "end_date": "2026-07-31"}, "next_next_month": {"start_date": "2026-07-01", "end_date": "2026-07-31"}}, "weekday": "Sunday"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 当前日期时间是：2026年5月17日 19:43:12，星期日（时区：Asia/Shanghai）。

关于明天（2026年5月18日，星期一）的公司会议安排，当前没有获得可用的工具返回结果。
