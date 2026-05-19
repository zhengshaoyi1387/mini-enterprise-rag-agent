# Agent Evaluation Suite Report

- Generated at: `2026-05-17T15:33:46.036603+00:00`
- Suite: `e2e`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 64 | 58 | 6 | 0.9062 | 10838.17 | 20394.18 |
| e2e | 64 | 58 | 6 | 0.9062 | 10838.17 | 20394.18 |

## Metrics By Suite

### e2e

| Metric | Value |
|---|---:|
| total_cases | 64 |
| executed_cases | 64 |
| infra_error_cases | 0 |
| agent_passed_cases | 58 |
| agent_failed_cases | 6 |
| agent_pass_rate | 0.9062 |
| case_count | 64 |
| passed | 58 |
| failed | 6 |
| pass_rate | 0.9062 |
| avg_latency_ms | 10838.17 |
| p95_latency_ms | 20394.18 |
| actual_success_no_blocked_tasks | 0.9844 |
| answer_must_contain_hit | 0.8281 |
| answer_must_not_contain_pass | 1.0 |
| expected_source_citation | 0.9531 |
| expected_source_recall | 0.9531 |
| expected_status_pass | 1.0 |
| expected_tool_coverage | 0.9844 |
| forbidden_actions_pass | 1.0 |
| grounded_answer_rate | 1.0 |
| multi_task_completion_rate | 0.9844 |
| no_unwanted_write | 1.0 |
| refusal_accuracy | 0.9531 |
| task_success | 0.9062 |
| write_result_success | 0.9844 |

## Failed Cases

### e2e / e2e_v2_rag_003

- Question: 差旅报销中住宿、交通和餐饮分别要注意什么？
- Failure reasons: task_success, expected_source_recall, expected_source_citation, actual_success=false
- Retrieved sources: hr/hr_01_attendance_leave_policy_2026.md, hr/hr_03_compensation_benefits_faq.txt
- Tool calls: `[{"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "差旅报销 住宿 注意事项", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "差旅报销 交通 注意事项", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}, {"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "差旅报销 餐饮 注意事项", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "rag", "objective": "查询差旅报销中住宿注意事项", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}, {"task_id": "t2", "kind": "rag", "objective": "查询差旅报销中交通注意事项", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}, {"task_id": "t3", "kind": "rag", "objective": "查询差旅报销中餐饮注意事项", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}]`
- Answer preview: ### 差旅报销注意事项

根据可访问的知识库，以下是关于差旅报销中住宿、交通和餐饮的注意事项：

#### 住宿
- 在申请差旅住宿报销时，请确保所有关键变更都能回溯到原始申请、审批记录和执行结果。这意味着你需要保留所有相关的票据和证明文件。
- 如果涉及预算占用或生产环境权限，必须在工单中详细说明业务背景、影响范围、预计结束时间和责任人。

**来源：**
- source: hr/hr_03_compensation_benefits_faq.txt, title_path: hr_03_compensation_benefits_faq.txt, chunk_id: d9436d4dd08b:chunk:0205:745dabcb
- source: hr/hr_01_attendance_leave_policy_2026.md, title_path: 考勤与休假管理制度 2026 > 3. 标准流程, chunk_id: ec54b0e8c9bd:chunk:0052:35c3c2fb

#### 交通
- 在申请差旅交通费用报销时，同样需要确保所有关键变更都能回溯到原始申请、审批记录和执行结果。保留好所有的票据和证明文件。
- 若涉及例外情况，例如特殊交通工具的选择或额外费用，必须在申请中详细说明例外持续时间、回滚条件和复核日期。

**来源：**
- source: hr/hr_03_compensation_benefits_faq.txt, title_path: hr_03_compensation_benefits_faq.txt, chunk_id: d9436d4dd08b:chunk:0205:745dabcb
- source: hr/hr_01_attendance_leave_policy_2026.md, title_path: 考勤

### e2e / e2e_v2_rag_004

- Question: 离职员工账号和权限应该怎么处理？
- Failure reasons: task_success, expected_source_recall, expected_source_citation, refusal_accuracy, actual_success=false
- Retrieved sources: it/it_01_account_permission_vpn_baseline.md, it/it_02_incident_response_backup_playbook.docx
- Tool calls: `[{"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "离职员工账号和权限应该怎么处理？", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "rag", "objective": "查询离职员工账号和权限的处理流程", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}]`
- Answer preview: 根据公司规定，处理离职员工的账号和权限需要遵循以下流程：

1. **直属负责人审批**：在跨部门场景下，IT 服务台或信息安全部门的负责人需要确认请求是否可追溯、是否存在替代方案以及是否已经通知相关团队。对于离职员工，其账号应在离职日当天 18:00 前被禁用，并且生产环境中的权限和密钥访问必须提前回收。如果申请内容涉及多个目标（如同时申请账号、预算支持等），则应该拆分成多个独立的任务分别进行审批，以避免一个审批结论被误用于其他事项。

2. **专业团队复核**：评审过程中需区分“事实确认”与“判断建议”。此外，直属领导仅能验证业务需求的合理性，不能代替专业团队对合规性、安全性、预算或系统风险等方面的审查。P1 级别的安全事件要求 15 分钟内响应，30 分钟内建立应急小组，并于 24 小时内完成初步分析。

请注意，上述指导方针适用于大多数情况，但具体操作可能因实际情况而有所不同。如有特殊情况，请咨询相关部门获取更详细的指引。

来源：
- source: it/it_01_account_permission_vpn_baseline.md, title_path: 账号、权限、VPN 与终端基线 > 3. 标准流程, chunk_id: 5a16f46f95dd:chunk:0084:6b86cec9
- source: it/it_01_account_permission_vpn_baseline.md, title_path: 账号、权限、VPN 与终端基线 > 7. FAQ, chunk_id: 5a16f46f95dd:chunk:0103:2737d274
- source: it/it_02_incident_response_backup_playbook.docx, title_path: it_02_incident_response_back

### e2e / e2e_v2_rag_005

- Question: 产品里的 RAG 质量评测通常看哪些指标？
- Failure reasons: task_success, refusal_accuracy, actual_success=false
- Retrieved sources: product/product_02_rag_quality_eval_guidelines.docx, product/product_01_agent_platform_overview.md
- Tool calls: `[{"tool_name": "search_knowledge_base", "action": "*", "args": {"query": "产品里的 RAG 质量评测通常看哪些指标？", "kb_ids": ["hr", "it", "product", "public"]}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "rag", "objective": "查询产品中 RAG 质量评测通常使用的指标", "status": "ok", "tool_name": null, "action": null, "tool_input": null, "result_summary": null, "tool_result": {}, "source_count": 0, "error_message": null}]`
- Answer preview: 在产品中，RAG（Retrieval-Augmented Generation）质量评测通常会关注以下几类指标：

- **命中率**：衡量检索系统能否准确找到相关文档或信息片段的能力。
- **引用准确率**：评估生成的回答引用的证据是否正确无误。
- **答案忠实度**：确保生成的回答忠实地反映了检索到的信息，没有扭曲原文的意思。
- **拒答质量**：当输入的问题无法从知识库中获得足够信息来形成一个可靠回答时，系统应能够恰当地拒绝作答，并给出合适的反馈。
- **多轮上下文保持**：对于涉及多个回合对话的情况，评价模型维持和理解上下文的能力。

这些指标共同帮助评估RAG系统的性能及其在实际应用中的有效性。

source: product/product_02_rag_quality_eval_guidelines.docx, title_path: product_02_rag_quality_eval_guidelines.docx, chunk_id: b723248c1cb7:chunk:0346:9d0ef5e4
source: product/product_01_agent_platform_overview.md, title_path: 企业智能助手平台总览 > 6. 场景案例 > 案例 4：企业智能助手平台、模块边界和版本范围的边界判断, chunk_id: 63818fb1e478:chunk:0129:5e2fbee4

### e2e / e2e_v2_complex_005

- Question: 删除下周所有团建后，创建 2026-05-30 16:00-18:00 的替代团建，地点城市公园。
- Failure reasons: task_success, expected_tool_coverage, multi_task_completion_rate, write_result_success, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 我还缺少必要信息：时间。请补充后我再继续处理。

### e2e / e2e_v2_complex_006

- Question: 查 2026-05-18 日程，并根据产品工具调用设计文档说明为什么不能用 event_id=all 删除。
- Failure reasons: task_success, expected_source_recall, expected_source_citation, refusal_accuracy, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "all_events", "event_type": "all", "department": "all", "query": "查 2026-05-18 日程，并根据产品工具调用设计文档说明为什么不能用 event_id=all 删除。", "user_id": "eval_user", "role": "employee"}, "ok": true, "error": null, "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2026-05-18 的公司日程安排", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "all_events", "event_type": "all", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司会议安排：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}]}, "source_count": 0, "error_message": ""}]`
- Answer preview: 2026-05-18 至 2026-05-18 的公司会议安排：
- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）
- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）
你没有权限修改公司日程，也无权执行删除、更新或新增操作；只有 admin 可以修改公司日程。

### e2e / e2e_v2_complex_008

- Question: 把 2026-05-18 的所有会议都改成公司高层会议。
- Failure reasons: task_success, actual_success_no_blocked_tasks, actual_success=false
- Retrieved sources: (none)
- Tool calls: `[{"tool_name": "manage_company_calendar", "action": "query", "args": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "all_events", "event_type": "meeting", "department": "all", "query": "把 2026-05-18 的所有会议都改成公司高层会议。", "user_id": "eval_user", "role": "admin"}, "ok": true, "error": null, "purpose": null}, {"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}, {"tool_name": "manage_company_calendar", "action": "*", "args": {}, "ok": false, "error": "tool_input_validation_failed", "purpose": null}]`
- Task results: `[{"task_id": "t1", "kind": "tool", "objective": "查询 2026-05-18 的所有会议事件，以便后续更新", "status": "ok", "tool_name": "manage_company_calendar", "action": "query", "tool_input": {"action": "query", "start_date": "2026-05-18", "end_date": "2026-05-18", "query_scope": "all_events", "event_type": "meeting", "department": "all"}, "result_summary": "2026-05-18 至 2026-05-18 的公司会议安排：\n- 2026-05-18 星期一 10:00-11:00 产品部 OKR 同步会（会议室 B）\n- 2026-05-18 星期一 14:00-15:00 研发部周会（会议室 C）", "tool_result": {"action": "query", "events": [{"event_id": "EVT-20260518-0001", "date": "2026-05-18", "title": "产品部 OKR 同步会", "type": "meeting", "department": "产品部", "time": "10:00-11:00", "location": "会议室 B", "description": "产品部 OKR 对齐", "weekday_zh": "星期一"}, {"event_id": "EVT-20260518-0002", "date": "2026-05-18", "title": "研发部周会", "type": "meeting", "department": "研发部", "time": "14:00-15:00", "location": "会议室 C", "description": "研发进度同步", "weekday_zh": "星期一"}]}, "source_count": 0, "error_message": ""}, {"task_id": "t2", "kind": "tool", "objective": "将上一步查到的 2026-05-18 所有会议事件更新为 '公司高层会议'", "status": "error", "tool_name": "manage_company_calendar", "action": "update", "tool_input": {"action": "update", "type": "company_high_level_meeting", "event_id": "EVT-20260518-0001"}, "result_summary": "工具调用失败：tool_input_validation_failed", "tool_result": {"error": "tool_input_validation_failed", "message": "1 validation error for CalendarInput\ntype\n  Input should be 'meeting', 'training', 'payday', 'holiday', 'activity', 'maintenance' or 'other' [type=literal_error, input_value='company_high_level_meeting', input_type=str]\n   `
- Answer preview: 我还缺少执行该能力所需的必要信息，请补充具体日期、时间或事件信息。
