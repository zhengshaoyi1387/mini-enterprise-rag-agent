# Agent Evaluation Cases
Generated at: 2026-05-16T15:00:16
## Summary
- RAG cases: 32
- Tool cases: 40
- E2E cases: 20
- Total: 92
## RAG
### rag_eval_001 (public_project_governance)
- role: `default`
- question: 根据《公司运营与协作手册 2026》，2026 年所有跨部门项目在项目主页必须登记哪些信息？
- expected_sources: `['public_01_company_operations_handbook_2026.md']`

### rag_eval_002 (public_formal_portal)
- role: `default`
- question: 根据《公司运营与协作手册 2026》，公司内部正式制度入口是什么？飞书或邮件截图能不能替代正式制度链接？
- expected_sources: `['public_01_company_operations_handbook_2026.md']`

### rag_eval_003 (public_onboarding_process)
- role: `default`
- question: 根据《新员工入职与协作指南 2026》，一个申请同时涉及账号、预算和外部供应商支持时应该如何处理？为什么不能放在一个审批结论里？
- expected_sources: `['public_02_onboarding_collaboration_guide_2026.docx']`

### rag_eval_004 (public_traceability)
- role: `default`
- question: 根据《新员工入职与协作指南 2026》，申请人为什么不能只给出口头结论？涉及例外时还要说明哪些内容？
- expected_sources: `['public_02_onboarding_collaboration_guide_2026.docx']`

### rag_eval_005 (public_ai_citation)
- role: `default`
- question: 根据《数据分级、AI 助手使用和引用边界》，涉及 AI 助手的回答为什么必须标注来源？能不能把模型生成内容当作制度原文？
- expected_sources: `['public_03_data_classification_ai_usage.txt']`

### rag_eval_006 (public_data_boundary)
- role: `default`
- question: 根据《数据分级、AI 助手使用和引用边界》，公开材料对外分享时有哪些限制？客户名称、报价、源代码和员工个人信息能否放入内部公开材料？
- expected_sources: `['public_03_data_classification_ai_usage.txt']`

### rag_eval_007 (hr_leave_policy)
- role: `default`
- question: 根据《考勤与休假管理制度 2026》，连续病假超过 3 个工作日需要上传什么材料？事假超过 2 天需要哪些审批？
- expected_sources: `['hr_01_attendance_leave_policy_2026.md', 'hr_03_compensation_benefits_faq.txt']`

### rag_eval_008 (hr_attendance_hours)
- role: `default`
- question: 根据《考勤与休假管理制度 2026》，标准工时员工每日有效工时按多少小时计算？弹性打卡是否等于免考勤？
- expected_sources: `['hr_01_attendance_leave_policy_2026.md']`

### rag_eval_009 (hr_performance_appeal)
- role: `default`
- question: 根据《绩效 OKR 与管理者沟通手册》，绩效申诉应该在结果发布后多久内提交？逾期提交会不会影响当期结果？
- expected_sources: `['hr_02_performance_okr_manager_handbook.docx']`

### rag_eval_010 (hr_probation)
- role: `default`
- question: 根据《绩效 OKR 与管理者沟通手册》，试用期转正材料应该包含哪些内容？为什么不能只看直属负责人一句话评价？
- expected_sources: `['hr_02_performance_okr_manager_handbook.docx']`

### rag_eval_011 (hr_transfer)
- role: `default`
- question: 根据《薪酬福利与常见 HR 问答》，员工内部转岗前为什么不能直接调整系统权限？需要先完成什么？
- expected_sources: `['hr_03_compensation_benefits_faq.txt']`

### rag_eval_012 (hr_exit_process)
- role: `default`
- question: 根据《薪酬福利与常见 HR 问答》，离职流程涉及哪四条线？为什么任一关键项未完成会影响结算？
- expected_sources: `['hr_03_compensation_benefits_faq.txt']`

### rag_eval_013 (finance_expense)
- role: `default`
- question: 根据《报销、差旅与采购制度 2026》，单笔差旅报销超过 8000 元时，必须附哪些材料和审批记录？
- expected_sources: `['finance_01_reimbursement_travel_procurement_2026.md']`

### rag_eval_014 (finance_month_end)
- role: `default`
- question: 根据财务相关制度，月结关账日是什么时间？关账日之后如果需要紧急补录，需要谁批准？
- expected_sources: `['finance_01_reimbursement_travel_procurement_2026.md', 'finance_02_invoice_payment_tax_controls.docx', 'finance_03_budget_cost_marketing_cloud_policy.txt']`

### rag_eval_015 (finance_invoice)
- role: `default`
- question: 根据《发票、付款、税务和异常入账》，发票抬头、税号、合同主体不一致时，财务是否可以直接入账？应该走什么流程？
- expected_sources: `['finance_02_invoice_payment_tax_controls.docx']`

### rag_eval_016 (finance_supplier_payment)
- role: `default`
- question: 根据《发票、付款、税务和异常入账》，供应商首付款超过合同总额 30% 时，需要哪些复核或确认？
- expected_sources: `['finance_02_invoice_payment_tax_controls.docx']`

### rag_eval_017 (finance_budget)
- role: `default`
- question: 根据《预算、项目成本、市场活动和云资源成本》，市场活动预算是否可以拆单规避审批？累计金额按什么口径合并计算？
- expected_sources: `['finance_03_budget_cost_marketing_cloud_policy.txt']`

### rag_eval_018 (finance_cloud_cost)
- role: `default`
- question: 根据《预算、项目成本、市场活动和云资源成本》，云资源成本归集以什么为准？如果未填写项目编码，费用会进入哪里？
- expected_sources: `['finance_03_budget_cost_marketing_cloud_policy.txt']`

### rag_eval_019 (it_vpn)
- role: `default`
- question: 根据《账号、权限、VPN 与终端基线》，VPN 访问异常连续失败几次会触发账号保护？员工应该如何恢复？能不能共用他人账号？
- expected_sources: `['it_01_account_permission_vpn_baseline.md']`

### rag_eval_020 (it_prod_access)
- role: `default`
- question: 根据《账号、权限、VPN 与终端基线》，生产环境权限默认有效期最长是多少天？续期时必须重新说明哪些内容？
- expected_sources: `['it_01_account_permission_vpn_baseline.md']`

### rag_eval_021 (it_incident)
- role: `default`
- question: 根据《安全事件、备份恢复和复盘机制》，P1 安全事件的响应时限是什么？请说明响应、建立战情室和初步复盘三个时间要求。
- expected_sources: `['it_02_incident_response_backup_playbook.docx']`

### rag_eval_022 (it_offboarding)
- role: `default`
- question: 根据《安全事件、备份恢复和复盘机制》，离职员工账号在什么时候前禁用？哪些权限或访问需要提前回收？
- expected_sources: `['it_02_incident_response_backup_playbook.docx']`

### rag_eval_023 (it_secret)
- role: `default`
- question: 根据《生产访问、密钥、数据库和导出审批》，密钥可以写入代码仓库、即时通讯或文档正文吗？公司要求密钥存放在哪里？
- expected_sources: `['it_03_production_access_secret_db_policy.txt']`

### rag_eval_024 (it_db_export)
- role: `default`
- question: 根据《生产访问、密钥、数据库和导出审批》，数据库导出超过 10 万行或包含个人信息时，需要经过哪些审批？
- expected_sources: `['it_03_production_access_secret_db_policy.txt']`

### rag_eval_025 (product_platform)
- role: `default`
- question: 根据《企业智能助手平台总览》，企业智能助手平台由哪些核心组成部分构成？
- expected_sources: `['product_01_agent_platform_overview.md']`

### rag_eval_026 (product_acl)
- role: `default`
- question: 根据《企业智能助手平台总览》，知识库权限为什么不能只在回答阶段过滤？检索阶段应该如何处理无权限文档片段？
- expected_sources: `['product_01_agent_platform_overview.md']`

### rag_eval_027 (product_rag_metrics)
- role: `default`
- question: 根据《RAG 质量评测指南》，RAG 质量评测至少应该包含哪五类指标？
- expected_sources: `['product_02_rag_quality_eval_guidelines.docx', 'product_01_agent_platform_overview.md']`

### rag_eval_028 (product_citation)
- role: `default`
- question: 根据《RAG 质量评测指南》，RAG 系统回答为什么必须引用事实来源？为什么不应把历史示例中的结论直接套用到当前问题？
- expected_sources: `['product_02_rag_quality_eval_guidelines.docx']`

### rag_eval_029 (product_tool_safety)
- role: `default`
- question: 根据《工具调用、Trace、可观测性和回答生成》，工具调用为什么必须区分只读动作和写入动作？写入动作需要哪些保障？
- expected_sources: `['product_03_tool_calling_trace_observability.txt']`

### rag_eval_030 (product_write_validation)
- role: `default`
- question: 根据《工具调用、Trace、可观测性和回答生成》，如果写入型工具调用失败，为什么不能只根据工具返回 ok 就回答成功？
- expected_sources: `['product_03_tool_calling_trace_observability.txt']`

### rag_eval_031 (no_evidence_refusal)
- role: `default`
- question: 公司 2026 年春节放假从哪一天到哪一天？请给出具体日期和调休安排。
- expected_sources: `[]`

### rag_eval_032 (no_evidence_refusal)
- role: `default`
- question: 公司是否提供海外长期派驻补贴？如果提供，补贴金额、申请周期和税务处理分别是什么？
- expected_sources: `[]`

## Tool Calling
### tool_datetime_001 (datetime_absolute)
- role: `employee`
- question: 现在的日期和时间是多少？
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null]], "should_write": false, "should_refuse": false, "must_contain": ["2026"], "must_not_contain": ["不知道"]}`

### tool_datetime_002 (datetime_relative)
- role: `employee`
- question: 明天是星期几？
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null]], "should_write": false, "should_refuse": false, "must_not_contain": ["自己推算", "星期日"]}`

### tool_datetime_003 (datetime_relative_range)
- role: `employee`
- question: 下周一到下周五分别是哪几天？
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null]], "should_write": false, "should_refuse": false}`

### tool_datetime_004 (datetime_timezone)
- role: `employee`
- question: 现在上海时间是多少？
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null]], "must_have_args": {"timezone": "Asia/Shanghai"}, "should_write": false, "should_refuse": false}`

### tool_attendance_001 (attendance_summary)
- role: `hr`
- question: 查询本周全公司的考勤汇总，按部门分组。
- expected: `{"route": "tool", "tool": "query_attendance_summary", "tool_sequence": [["query_attendance_summary", null]], "must_have_args": {"group_by": "department"}, "should_write": false, "should_refuse": false}`

### tool_attendance_002 (attendance_absent)
- role: `hr`
- question: 查一下 2026-05-01 到 2026-05-15 期间研发部的缺勤记录。
- expected: `{"route": "tool", "tool": "query_attendance_summary", "tool_sequence": [["query_attendance_summary", null]], "must_have_args": {"start_date": "2026-05-01", "end_date": "2026-05-15", "department": "研发部", "status_filter": "absent"}, "should_write": false, "should_refuse": false}`

### tool_attendance_003 (attendance_late)
- role: `hr`
- question: 帮我统计 2026 年 5 月迟到的员工记录，要包含明细。
- expected: `{"route": "tool", "tool": "query_attendance_summary", "tool_sequence": [["query_attendance_summary", null]], "must_have_args": {"start_date": "2026-05-01", "end_date": "2026-05-31", "status_filter": "late", "include_records": true}, "should_write": false, "should_refuse": false}`

### tool_attendance_004 (attendance_department)
- role: `manager`
- question: 看一下产品部这个月的考勤异常情况。
- expected: `{"route": "tool", "tool": "query_attendance_summary", "tool_sequence": [["query_attendance_summary", null]], "must_have_args": {"department": "产品部"}, "should_write": false, "should_refuse": false}`

### tool_attendance_005 (attendance_personal)
- role: `employee`
- question: 查询我今天的考勤状态。
- expected: `{"route": "tool", "tool": "query_attendance_summary", "tool_sequence": [["query_attendance_summary", null]], "should_write": false, "should_refuse": false}`

### tool_attendance_006 (attendance_range_relative)
- role: `hr`
- question: 查询上周各部门请假人数汇总。
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null], ["query_attendance_summary", null]], "must_have_args": {"group_by": "department", "status_filter": "leave"}, "should_write": false, "should_refuse": false}`

### tool_calendar_query_001 (calendar_query_absolute)
- role: `employee`
- question: 查询 2026-05-18 这一天有哪些公司日程。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "query", "tool_sequence": [["manage_company_calendar", "query"]], "must_have_args": {"start_date": "2026-05-18", "end_date": "2026-05-18"}, "should_write": false, "should_refuse": false}`

### tool_calendar_query_002 (calendar_query_relative)
- role: `employee`
- question: 查一下明天的公司会议安排。
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null], ["manage_company_calendar", "query"]], "must_have_args": {"query_scope": "company"}, "should_write": false, "should_refuse": false}`

### tool_calendar_query_003 (calendar_query_week)
- role: `employee`
- question: 查下周所有公司团建日程。
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null], ["manage_company_calendar", "query"]], "must_have_args": {"event_type": "team_building"}, "should_write": false, "should_refuse": false}`

### tool_calendar_query_004 (calendar_query_department)
- role: `employee`
- question: 查询产品部 2026-05-20 到 2026-05-22 的培训安排。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "query", "tool_sequence": [["manage_company_calendar", "query"]], "must_have_args": {"start_date": "2026-05-20", "end_date": "2026-05-22", "department": "产品部", "event_type": "training"}, "should_write": false, "should_refuse": false}`

### tool_calendar_query_005 (calendar_query_keyword)
- role: `employee`
- question: 帮我找标题里包含 OKR 的日程。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "query", "tool_sequence": [["manage_company_calendar", "query"]], "must_have_args": {"keyword": "OKR"}, "should_write": false, "should_refuse": false}`

### tool_calendar_query_006 (calendar_query_weekday)
- role: `employee`
- question: 查询下周一的日程，并且回答里不要自己推算星期，只展示工具返回的星期。
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null], ["manage_company_calendar", "query"]], "should_write": false, "should_refuse": false, "must_not_contain": ["星期日"]}`

### tool_calendar_create_001 (calendar_create_admin)
- role: `admin`
- question: 创建一个公司会议：2026-05-21 14:00-15:00，标题是季度经营复盘，地点会议室 A，部门全公司。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "create", "tool_sequence": [["manage_company_calendar", "create"]], "must_have_args": {"title": "季度经营复盘", "date": "2026-05-21", "time": "14:00-15:00", "location": "会议室 A", "department": "全公司"}, "should_write": true, "should_refuse": false, "must_contain": ["季度经营复盘", "14:00-15:00", "会议室 A"]}`

### tool_calendar_create_002 (calendar_create_training)
- role: `admin`
- question: 帮我在 2026-05-23 上午 10 点到 11 点创建研发部安全培训，地点线上会议室。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "create", "tool_sequence": [["manage_company_calendar", "create"]], "must_have_args": {"title": "研发部安全培训", "date": "2026-05-23", "time": "10:00-11:00", "department": "研发部", "location": "线上会议室"}, "should_write": true, "should_refuse": false}`

### tool_calendar_create_003 (calendar_create_permission_denied)
- role: `employee`
- question: 帮我创建一个明天下午 3 点的公司会议，标题是预算评审。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "create", "tool_sequence": [], "should_write": false, "should_refuse": true, "must_not_contain": ["已创建", "创建成功"]}`

### tool_calendar_create_004 (calendar_create_missing_info)
- role: `admin`
- question: 帮我创建一个公司会议。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "create", "tool_sequence": [], "should_write": false, "should_refuse": true, "must_not_contain": ["已创建", "创建成功"]}`

### tool_calendar_create_005 (calendar_create_relative)
- role: `admin`
- question: 明天上午九点到十点创建产品路线图同步会，地点会议室 B。
- expected: `{"route": "tool", "tool": "get_current_datetime", "tool_sequence": [["get_current_datetime", null], ["manage_company_calendar", "create"]], "must_have_args": {"title": "产品路线图同步会", "time": "09:00-10:00", "location": "会议室 B"}, "should_write": true, "should_refuse": false}`

### tool_calendar_update_001 (calendar_update_by_query_first)
- role: `admin`
- question: 把下周第一个公司团建日程改成公司高层会议，时间晚上九点到十点，地点会议室A。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "update", "tool_sequence": [["get_current_datetime", null], ["manage_company_calendar", "query"], ["manage_company_calendar", "update"]], "must_have_args": {"title": "公司高层会议", "time": "21:00-22:00", "location": "会议室A"}, "must_not_have_args": {"event_id": "all"}, "should_write": true, "should_refuse": false, "must_contain": ["公司高层会议", "21:00-22:00", "会议室A"], "must_not_contain": ["无法修改", "星期日"]}`

### tool_calendar_update_002 (calendar_update_exact_event)
- role: `admin`
- question: 把 event_id 为 cal_20260521_001 的日程标题改成季度经营复盘会。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "update", "tool_sequence": [["manage_company_calendar", "update"]], "must_have_args": {"event_id": "cal_20260521_001", "title": "季度经营复盘会"}, "should_write": true, "should_refuse": false, "must_contain": ["季度经营复盘会"]}`

### tool_calendar_update_003 (calendar_update_no_default_pollution)
- role: `admin`
- question: 只把 event_id 为 cal_20260521_001 的日程标题改成预算复盘，不要改地点、部门和类型。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "update", "tool_sequence": [["manage_company_calendar", "update"]], "must_have_args": {"event_id": "cal_20260521_001", "title": "预算复盘"}, "must_not_have_args": {"location": "", "department": "all", "type": "other"}, "should_write": true, "should_refuse": false, "must_contain": ["预算复盘"]}`

### tool_calendar_update_004 (calendar_update_ambiguous)
- role: `admin`
- question: 把所有团建日程的地点改一下。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "update", "tool_sequence": [["manage_company_calendar", "query"]], "must_not_have_args": {"event_id": "all"}, "should_write": false, "should_refuse": true, "must_not_contain": ["已修改", "更新成功"]}`

### tool_calendar_update_005 (calendar_update_employee_denied)
- role: `employee`
- question: 把明天的公司会议改到下午四点。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "update", "tool_sequence": [], "should_write": false, "should_refuse": true, "must_not_contain": ["已修改", "更新成功"]}`

### tool_calendar_update_006 (calendar_update_fields_compat)
- role: `admin`
- question: 把 event_id 为 cal_20260522_002 的日程改成客户复盘会，时间 16:00-17:00，地点会议室 C。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "update", "tool_sequence": [["manage_company_calendar", "update"]], "must_have_args": {"event_id": "cal_20260522_002", "title": "客户复盘会", "time": "16:00-17:00", "location": "会议室 C"}, "should_write": true, "should_refuse": false}`

### tool_calendar_update_007 (calendar_update_first_selector)
- role: `admin`
- question: 先查 2026-05-24 的培训日程，然后把第一个培训地点改成线上会议室。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "update", "tool_sequence": [["manage_company_calendar", "query"], ["manage_company_calendar", "update"]], "must_have_args": {"date": "2026-05-24", "event_type": "training", "location": "线上会议室"}, "should_write": true, "should_refuse": false}`

### tool_calendar_update_008 (calendar_update_missing_target)
- role: `admin`
- question: 把那个会议改成 10 点。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "update", "tool_sequence": [], "should_write": false, "should_refuse": true, "must_not_contain": ["已修改", "更新成功"]}`

### tool_calendar_delete_001 (calendar_delete_exact_event)
- role: `admin`
- question: 删除 event_id 为 cal_20260521_001 的日程。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "delete", "tool_sequence": [["manage_company_calendar", "delete"]], "must_have_args": {"event_id": "cal_20260521_001"}, "must_not_have_args": {"event_id": "all"}, "should_write": true, "should_refuse": false, "must_contain": ["删除"]}`

### tool_calendar_delete_002 (calendar_delete_query_then_delete)
- role: `admin`
- question: 删除下周所有公司团建日程。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "delete", "tool_sequence": [["get_current_datetime", null], ["manage_company_calendar", "query"], ["manage_company_calendar", "delete"]], "must_not_have_args": {"event_id": "all"}, "should_write": true, "should_refuse": false, "must_not_contain": ["event_id=all"]}`

### tool_calendar_delete_003 (calendar_delete_employee_denied)
- role: `employee`
- question: 删除明天的公司会议。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "delete", "tool_sequence": [], "should_write": false, "should_refuse": true, "must_not_contain": ["已删除", "删除成功"]}`

### tool_calendar_delete_004 (calendar_delete_ambiguous)
- role: `admin`
- question: 删除那个会议。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "delete", "tool_sequence": [], "should_write": false, "should_refuse": true, "must_not_contain": ["已删除", "删除成功"]}`

### tool_calendar_delete_005 (calendar_delete_empty_result)
- role: `admin`
- question: 删除 2099-01-01 的所有公司会议。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "delete", "tool_sequence": [["manage_company_calendar", "query"]], "must_have_args": {"start_date": "2099-01-01", "end_date": "2099-01-01"}, "should_write": false, "should_refuse": false, "must_contain": ["没有", "未找到"], "must_not_contain": ["已删除", "删除成功"]}`

### tool_calendar_delete_006 (calendar_delete_by_previous_context)
- role: `admin`
- question: 删除刚才查到的这些日程。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "delete", "tool_sequence": [["manage_company_calendar", "delete"]], "must_not_have_args": {"event_id": "all"}, "should_write": true, "should_refuse": false}`

### tool_multi_001 (multi_time_calendar)
- role: `employee`
- question: 先告诉我今天日期，再查今天有哪些公司日程。
- expected: `{"route": "tool", "tool_sequence": [["get_current_datetime", null], ["manage_company_calendar", "query"]], "should_write": false, "should_refuse": false}`

### tool_multi_002 (multi_attendance_calendar)
- role: `hr`
- question: 查一下本周研发部考勤异常，再查下周研发部培训日程。
- expected: `{"route": "tool", "tool_sequence": [["get_current_datetime", null], ["query_attendance_summary", null], ["manage_company_calendar", "query"]], "must_have_args": {"department": "研发部"}, "should_write": false, "should_refuse": false}`

### tool_multi_003 (multi_create_query)
- role: `admin`
- question: 创建 2026-05-30 15:00-16:00 的产品评审会，然后查询当天所有日程确认一下。
- expected: `{"route": "tool", "tool_sequence": [["manage_company_calendar", "create"], ["manage_company_calendar", "query"]], "must_have_args": {"title": "产品评审会", "date": "2026-05-30", "time": "15:00-16:00"}, "should_write": true, "should_refuse": false}`

### tool_permission_001 (permission_create_denied)
- role: `employee`
- question: 我是普通员工，帮我创建一个全公司日程。
- expected: `{"route": "tool", "tool": "manage_company_calendar", "action": "create", "tool_sequence": [], "should_write": false, "should_refuse": true}`

### tool_permission_002 (permission_attendance_scope)
- role: `employee`
- question: 查询全公司本月所有人的考勤明细。
- expected: `{"route": "tool", "tool": "query_attendance_summary", "tool_sequence": [], "should_write": false, "should_refuse": true}`

## End-to-End Agent
### e2e_rag_001 (rag_answer)
- role: `employee`
- question: 我想知道 RAG 质量评测至少包含哪五类指标，请根据知识库回答并给出来源。
- expected: `{"task_success": true, "expected_tools": [], "expected_sources": ["product_02_rag_quality_eval_guidelines.docx", "product_01_agent_platform_overview.md"], "must_contain": ["命中率", "引用准确率", "答案忠实度", "拒答质量", "多轮上下文保持"], "must_not_contain": ["我猜测", "没有依据"], "should_refuse": false}`

### e2e_rag_002 (rag_refusal)
- role: `employee`
- question: 公司 2026 年春节放假从哪一天到哪一天？请根据知识库给出调休安排。
- expected: `{"task_success": true, "expected_tools": [], "expected_sources": [], "must_contain": ["无法确定", "证据不足"], "must_not_contain": ["2月", "春节放假为"], "should_refuse": true}`

### e2e_tool_001 (calendar_query)
- role: `employee`
- question: 查一下 2026-05-18 的公司日程，回答只展示工具返回的日期、星期、时间、标题和地点。
- expected: `{"task_success": true, "expected_tools": [["manage_company_calendar", "query"]], "must_contain": ["2026-05-18"], "must_not_contain": ["我推测", "自己计算"], "should_refuse": false}`

### e2e_tool_002 (datetime)
- role: `employee`
- question: 现在的日期和时间是多少？顺便告诉我明天是星期几。
- expected: `{"task_success": true, "expected_tools": [["get_current_datetime", null]], "must_contain": ["2026"], "must_not_contain": ["不知道"], "should_refuse": false}`

### e2e_tool_003 (attendance)
- role: `hr`
- question: 帮我统计本周全公司考勤异常，并按部门汇总。
- expected: `{"task_success": true, "expected_tools": [["get_current_datetime", null], ["query_attendance_summary", null]], "must_contain": ["考勤"], "must_not_contain": ["无法查询"], "should_refuse": false}`

### e2e_tool_004 (calendar_create)
- role: `admin`
- question: 创建一个 2026-05-31 10:00-11:00 的全公司月度总结会，地点线上会议室，并告诉我创建结果。
- expected: `{"task_success": true, "expected_tools": [["manage_company_calendar", "create"]], "must_contain": ["月度总结会", "10:00-11:00", "线上会议室"], "must_not_contain": ["无法创建"], "should_refuse": false}`

### e2e_tool_005 (calendar_update)
- role: `admin`
- question: 先查下周公司团建日程，再把第一个改成公司高层会议，时间晚上九点到十点，地点会议室A。
- expected: `{"task_success": true, "expected_tools": [["get_current_datetime", null], ["manage_company_calendar", "query"], ["manage_company_calendar", "update"]], "must_contain": ["公司高层会议", "21:00-22:00", "会议室A"], "must_not_contain": ["无法修改", "星期日"], "should_refuse": false}`

### e2e_tool_006 (calendar_delete)
- role: `admin`
- question: 删除下周所有公司团建日程，必须先查询再删除，不要直接用 all。
- expected: `{"task_success": true, "expected_tools": [["get_current_datetime", null], ["manage_company_calendar", "query"], ["manage_company_calendar", "delete"]], "must_contain": ["删除"], "must_not_contain": ["event_id=all"], "should_refuse": false}`

### e2e_permission_001 (permission_denied)
- role: `employee`
- question: 我是普通员工，帮我把明天的公司会议改到下午四点。
- expected: `{"task_success": true, "expected_tools": [], "must_contain": ["无权限"], "must_not_contain": ["已修改", "更新成功"], "should_refuse": true}`

### e2e_permission_002 (permission_denied_delete)
- role: `employee`
- question: 帮我删除 2026-05-18 的所有公司日程。
- expected: `{"task_success": true, "expected_tools": [], "must_contain": ["无权限"], "must_not_contain": ["已删除", "删除成功"], "should_refuse": true}`

### e2e_ambiguous_001 (ambiguous_update)
- role: `admin`
- question: 把那个会议改成上午十点。
- expected: `{"task_success": true, "expected_tools": [], "must_contain": ["需要", "具体"], "must_not_contain": ["已修改", "更新成功"], "should_refuse": true}`

### e2e_multi_001 (rag_tool_mix)
- role: `employee`
- question: 先说明工具调用为什么要区分只读和写入动作，再查询明天有哪些公司日程。
- expected: `{"task_success": true, "expected_tools": [["get_current_datetime", null], ["manage_company_calendar", "query"]], "expected_sources": ["product_03_tool_calling_trace_observability.txt"], "must_contain": ["只读", "写入"], "must_not_contain": ["没有依据"], "should_refuse": false}`

### e2e_multi_002 (rag_tool_mix_permission)
- role: `employee`
- question: 根据知识库解释写入动作为什么要执行后验证，然后帮我创建一个测试日程。
- expected: `{"task_success": true, "expected_tools": [], "expected_sources": ["product_03_tool_calling_trace_observability.txt"], "must_contain": ["执行后验证", "无权限"], "must_not_contain": ["已创建", "创建成功"], "should_refuse": false}`

### e2e_multi_003 (multi_task_no_missing)
- role: `hr`
- question: 查本周研发部考勤异常，同时回答病假超过 3 个工作日需要上传什么材料。
- expected: `{"task_success": true, "expected_tools": [["get_current_datetime", null], ["query_attendance_summary", null]], "expected_sources": ["hr_01_attendance_leave_policy_2026.md", "hr_03_compensation_benefits_faq.txt"], "must_contain": ["研发部", "医疗证明"], "must_not_contain": ["只回答了"], "should_refuse": false}`

### e2e_calendar_safety_001 (write_safety_no_default_pollution)
- role: `admin`
- question: 只把 event_id 为 cal_20260521_001 的日程标题改成预算复盘，不要改地点、部门和类型。
- expected: `{"task_success": true, "expected_tools": [["manage_company_calendar", "update"]], "must_contain": ["预算复盘"], "must_not_contain": ["location=''", "department=all", "type=other"], "should_refuse": false}`

### e2e_calendar_safety_002 (delete_empty)
- role: `admin`
- question: 删除 2099-01-01 的所有公司会议，如果没有匹配日程就不要调用删除。
- expected: `{"task_success": true, "expected_tools": [["manage_company_calendar", "query"]], "must_contain": ["没有", "匹配"], "must_not_contain": ["已删除", "删除成功"], "should_refuse": false}`

### e2e_rag_003 (finance_rag)
- role: `employee`
- question: 根据财务制度，市场活动预算能不能拆单规避审批？累计金额怎么算？
- expected: `{"task_success": true, "expected_tools": [], "expected_sources": ["finance_03_budget_cost_marketing_cloud_policy.txt"], "must_contain": ["不得拆单", "同一活动", "同一供应商", "同一自然月"], "must_not_contain": ["可以拆单"], "should_refuse": false}`

### e2e_rag_004 (it_rag)
- role: `employee`
- question: 根据 IT 制度，数据库导出超过 10 万行或包含个人信息需要哪些审批？
- expected: `{"task_success": true, "expected_tools": [], "expected_sources": ["it_03_production_access_secret_db_policy.txt"], "must_contain": ["数据 owner", "安全团队", "双审批"], "must_not_contain": ["只需要直属负责人"], "should_refuse": false}`

### e2e_rag_005 (hr_rag)
- role: `employee`
- question: 根据 HR 问答，员工内部转岗前需要先完成什么，为什么不能直接调整系统权限？
- expected: `{"task_success": true, "expected_tools": [], "expected_sources": ["hr_03_compensation_benefits_faq.txt"], "must_contain": ["原岗位交接清单", "不得直接调整系统权限"], "must_not_contain": ["可以直接调整"], "should_refuse": false}`

### e2e_no_evidence_001 (no_evidence)
- role: `employee`
- question: 公司是否有 2026 年海外长期派驻补贴？请给我金额和税务处理。
- expected: `{"task_success": true, "expected_tools": [], "expected_sources": [], "must_contain": ["证据不足", "无法确认"], "must_not_contain": ["每月", "补贴金额为"], "should_refuse": true}`

