# Agent Evaluation Suite Report

- Generated at: `2026-05-17T11:33:48.715806+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 12 | 8 | 4 | 0.6667 | 17483.24 | 29311.55 |
| e2e | 12 | 8 | 4 | 0.6667 | 17483.24 | 29311.55 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 12 |
| executed_cases | 12 |
| infra_error_cases | 0 |
| agent_passed_cases | 8 |
| agent_failed_cases | 4 |
| agent_pass_rate | 0.6667 |
| case_count | 12 |
| passed | 8 |
| failed | 4 |
| pass_rate | 0.6667 |
| avg_latency_ms | 17483.24 |
| p95_latency_ms | 29311.55 |
| actual_success_no_blocked_tasks | 0.9167 |
| answer_must_contain_hit | 0.9167 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 1.0 |
| expected_source_recall | 1.0 |
| expected_tool_coverage | 0.6667 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 0.6667 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 0.8333 |
| task_success | 0.6667 |
| write_result_success | 1.0 |

## Failed Cases

### e2e / e2e_tool_001

- Question: 先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。
- Failure reasons: task_success, expected_tool_coverage, multi_task_completion_rate, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai"}, "ok": true, "error": null, "purpose": "resolve_time_reference"}, {"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "type_filtered", "event_type": "activity", "department": "all", "query": "先查下周所有公司团建日程，再把第一个改成公司高层会议，时间 21:00-22:00，地点会议室A。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询下周所有公司团建日程", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-24", "query_scope": "type_filtered", "event_type": "activity", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-24 的公司日程：\n- 2026-05-19 星期二 16:00-18:00 公司团建（城市公园，event_id：EVT-20260519-0001）\n- 2026-05-21 星期四 18:00-20:00 公司团建（团建餐厅，event_id：EVT-20260521-0002）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260519-0001", "date": "2026-05-19", "title": "公司团建", "type": "activity", "department": "all", "time": "16:00-18:00", "location": "城市公园", "description": "下周第一个团建活动，用于 update/delete 评测", "weekday_zh": "星期二"}, {"event_id": "EVT-20260521-0002", "date": "2026-05-21", "title": "公司团建", "type": "activity", "department": "all", "time": "18:00-20:00", "location": "团建餐厅", "description": "第二个团建活动", "weekday_zh": "星期四"}]}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "将查询结果中的第一条团建日程更新为公司高层会议（21:00-22:00，会议室A）", "status": "needs_clarification", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "event_id": "", "start_date": "", "end_date": "", "title": "公司高层会议", "location": "会议室A", "description": "", "event_type": "meeting"}, "result_summary": "匹配到多个日程，请指定要更新的 event_id 后再修改。", "tool_result": {"action": "update", "status": "needs_clarification", "message": "匹配到多个日程，请指定要更新的 event_id 后再修改。"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据已完成的任务和工具结果，回答如下：

### 1. 下周公司团建日程查询结果  
在 2026-05-18 至 2026-05-24 期间，共有以下两个公司团建日程：  
- **2026-05-19 星期二 16:00–18:00**：公司团建（城市公园，event_id：EVT-20260519-0001）  
- **2026-05-21 星期四 18:00–20:00**：公司团建（团建餐厅，event_id：EVT-20260521-0002）

### 2. 修改第一个团建日程为公司高层会议  
系统提示：“匹配到多个日程，请指定要更新的 event_id 后再修改。”  
虽然您希望修改“第一个”团建日程，但为确保操作准确，需明确提供要修改的日程 **event_id**。  

如果您确认要修改的是 **2026-05-19 的团建（event_id: EVT-20260519-0001）**，请明确说明，即可将其更新为：  
- **标题**：公司高层会议  
- **时间**：21:00–22:00  
- **地点**：会议室A

### e2e / e2e_tool_002

- Question: 先查 2026-05-24 的培训日程，再把第一个培训地点改成线上会议室。
- Failure reasons: task_success, expected_tool_coverage, refusal_accuracy, multi_task_completion_rate, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-24", "end_date": "2026-05-24", "query_scope": "all_events", "event_type": "training", "department": "all", "query": "先查 2026-05-24 的培训日程，再把第一个培训地点改成线上会议室。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2026-05-24 的培训日程", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-24", "end_date": "2026-05-24", "query_scope": "all_events", "event_type": "training", "department": "all"}, "result_summary": "2026-05-24 至 2026-05-24 的公司日程：\n- 2026-05-24 星期日 10:00-12:00 新员工产品培训（培训室 2，event_id：EVT-20260524-0001）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260524-0001", "date": "2026-05-24", "title": "新员工产品培训", "type": "training", "department": "产品部", "time": "10:00-12:00", "location": "培训室 2", "description": "用于 query-first update 评测", "weekday_zh": "星期日"}]}, "source_count": 0, "error_message": ""}]`
- Answer preview: 已查询到 2026-05-24（星期日）有一场培训日程：

- **新员工产品培训**  
  时间：10:00-12:00  
  原地点：培训室 2  
  event_id：EVT-20260524-0001

接下来，将该培训的地点修改为“线上会议室”。

正在执行更新操作……  

（注：根据当前提供的信息，系统已完成查询，但尚未执行更新操作。由于用户要求“再把第一个培训地点改成线上会议室”，而当前仅提供了查询结果，未包含更新后的工具返回，因此无法确认修改是否成功。若需完成此操作，应调用 `manage_company_calendar` 的 `update` 动作并提供 event_id 和新 location。）

### e2e / e2e_tool_006

- Question: 查询明天公司会议安排，然后告诉我能不能删除它。
- Failure reasons: task_success, expected_tool_coverage, refusal_accuracy, multi_task_completion_rate, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2025-04-09", "end_date": "2025-04-09", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "查询明天公司会议安排，然后告诉我能不能删除它。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询明天公司会议安排", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2025-04-09", "end_date": "2025-04-09", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2025-04-09 至 2025-04-09 暂无公司日程。", "tool_result": {"action": "query", "events": []}, "source_count": 0, "error_message": ""}]`
- Answer preview: 根据工具查询结果，2025年4月9日（明天）暂无公司会议安排。

由于没有查询到相关会议，因此不存在删除操作的对象。此外，当前角色在公司日历管理中仅具备查询权限，无权删除公司日程。

### e2e / e2e_tool_008

- Question: 现在的日期时间是多少？顺便查一下明天的公司会议安排。
- Failure reasons: task_success, expected_tool_coverage, answer_must_contain_hit, multi_task_completion_rate, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "get_current_datetime", "action": "*", "args": {"timezone": "Asia/Shanghai", "query": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "现在的日期时间是多少？顺便查一下明天的公司会议安排。", "status": "ok", "tool_name": "get_current_datetime", "action": "*", "tool_input": {"timezone": "Asia/Shanghai"}, "result_summary": "当前日期：2026-05-17，时间：19:32:35，星期：Sunday，时区：Asia/Shanghai。", "tool_result": {"ranges": {"today": {"start_date": "2026-05-17", "end_date": "2026-05-17"}, "yesterday": {"start_date": "2026-05-16", "end_date": "2026-05-16"}, "tomorrow": {"start_date": "2026-05-18", "end_date": "2026-05-18"}, "day_after_tomorrow": {"start_date": "2026-05-19", "end_date": "2026-05-19"}, "this_week": {"start_date": "2026-05-11", "end_date": "2026-05-17"}, "last_week": {"start_date": "2026-05-04", "end_date": "2026-05-10"}, "next_week": {"start_date": "2026-05-18", "end_date": "2026-05-24"}, "week_after_next": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "next_next_week": {"start_date": "2026-05-25", "end_date": "2026-05-31"}, "this_month": {"start_date": "2026-05-01", "end_date": "2026-05-31"}, "last_month": {"start_date": "2026-04-01", "end_date": "2026-04-30"}, "next_month": {"start_date": "2026-06-01", "end_date": "2026-06-30"}, "month_after_next": {"start_date": "2026-07-01", "end_date": "2026-07-31"}, "next_next_month": {"start_date": "2026-07-01", "end_date": "2026-07-31"}}, "weekday": "Sunday", "timezone": "Asia/Shanghai", "current_time": "19:32:35", "current_date": "2026-05-17", "weekday_zh": "星期日"}, "source_count": 0, "error_message": ""}]`
- Answer preview: 当前日期时间是：2026年5月17日 19:32:35，星期日（时区：Asia/Shanghai）。

关于明天（2026年5月18日，星期一）的公司会议安排，当前没有获得相关工具返回的会议信息。
