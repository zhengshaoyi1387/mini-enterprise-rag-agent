# 长文档企业知识库 RAG 评测问题集

这份问题集按当前项目 `src/mini_rag/eval.py` 的字段设计：`question`、`expected_sources`、`should_refuse` 是主字段，其他字段用于人工复盘。

> 注意：当前项目 loader 只索引 `.md` / `.markdown` / `.txt` / `.pdf` / `.docx`，所以主问题集没有把 `.json` / `.yaml` / `.csv` 作为 expected_sources。

## 统计

- 总问题数：30
- 覆盖目录：public / hr / finance / it / product
- 覆盖格式：md / docx / txt
- 覆盖类型：精确事实、制度边界、相似条款区分、跨文档多跳、无证据拒答

## 问题清单

| ID | 类型 | 难度 | 问题 | 期望来源 | 期望要点 |
|---|---|---|---|---|---|
| rag_long_001 | public_exact_fact | easy | 根据公司运营与协作手册，2026 年所有跨部门项目在项目主页必须登记哪些信息？ | public_01_company_operations_handbook_2026.md | 目标；负责人；里程碑；风险状态 |
| rag_long_002 | public_policy_boundary | medium | 内部公开材料对外分享时有哪些限制？客户名称、报价、源代码和员工个人信息能不能放进去？ | public_01_company_operations_handbook_2026.md | 公开材料可以对外分享；内部公开材料不得包含客户名称、报价、源代码或员工个人信息 |
| rag_long_003 | public_process | medium | 新员工入职与协作指南里说，如果一个申请同时涉及账号、预算和外部供应商支持，应该如何处理，为什么不能放在一个审批结论里？ | public_02_onboarding_collaboration_guide_2026.docx | 拆成多个任务分别审批；避免一个审批结论被误用到其他事项 |
| rag_long_004 | public_ai_usage | medium | 涉及 AI 助手的回答为什么必须标注来源？能不能把模型生成内容当作制度原文？ | public_03_data_classification_ai_usage.txt | 必须标注来源；不能把模型生成内容当作制度原文 |
| rag_long_005 | public_disambiguation | medium | 公共模板是否可以代表审批已经完成？如果不能，审批结论应该来自哪里？ | public_01_company_operations_handbook_2026.md | 公共模板只规定格式；不代表审批完成；审批结论必须来自对应业务系统 |
| rag_long_006 | public_exact_fact | easy | 公司内部正式制度入口是什么？飞书或邮件截图能不能替代正式制度链接？ | public_02_onboarding_collaboration_guide_2026.docx | 星河协同门户；飞书或邮件截图不能替代正式制度链接 |
| rag_long_007 | hr_leave_policy | easy | 考勤与休假制度中，连续病假超过 3 个工作日需要上传什么材料？事假超过 2 天需要哪些审批？ | hr_01_attendance_leave_policy_2026.md | 医疗证明；直属负责人；HRBP 双审批 |
| rag_long_008 | hr_attendance_policy | easy | 标准工时员工每日有效工时按多少小时计算？弹性打卡是否等于免考勤？ | hr_01_attendance_leave_policy_2026.md | 8 小时；弹性打卡不等于免考勤 |
| rag_long_009 | hr_performance_appeal | medium | 绩效 OKR 手册中，绩效申诉应该在结果发布后多久内提交？逾期提交会不会影响当期结果？ | hr_02_performance_okr_manager_handbook.docx | 5 个工作日内；逾期只进入复盘记录；不影响当期结果 |
| rag_long_010 | hr_probation | medium | 试用期转正材料应该包含哪些内容？为什么不能只看直属负责人一句话评价？ | hr_02_performance_okr_manager_handbook.docx | 目标完成度；协作反馈；风险事项；不能只看直属负责人一句话评价 |
| rag_long_011 | hr_transfer_boundary | medium | 员工内部转岗前，为什么不能直接调整系统权限？需要先完成什么？ | hr_03_compensation_benefits_faq.txt | 先完成原岗位交接清单；未交接完成不得直接调整系统权限 |
| rag_long_012 | hr_exit_process | medium | 离职流程涉及哪四条线？为什么任一关键项未完成会影响结算？ | hr_03_compensation_benefits_faq.txt | 薪资；设备；账号；知识交接；阻塞结算 |
| rag_long_013 | finance_travel_expense | easy | 单笔差旅报销超过 8000 元时，必须附哪些材料和审批记录？ | finance_01_reimbursement_travel_procurement_2026.md | 行程单；发票；支付凭证；直属负责人审批记录 |
| rag_long_014 | finance_invoice_control | medium | 发票抬头、税号、合同主体不一致时，财务是否可以直接入账？应该走什么流程？ | finance_02_invoice_payment_tax_controls.docx | 不得直接入账；异常发票处理流程 |
| rag_long_015 | finance_supplier_payment | medium | 供应商首付款超过合同总额 30% 时，需要哪些复核或确认？ | finance_02_invoice_payment_tax_controls.docx | 财务复核；法务确认付款条件 |
| rag_long_016 | finance_budget_disambiguation | medium | 市场活动预算是否可以拆单规避审批？累计金额按什么口径合并计算？ | finance_03_budget_cost_marketing_cloud_policy.txt | 不得拆单规避审批；同一活动；同一供应商；同一自然月 |
| rag_long_017 | finance_month_end | easy | 月结关账日是什么时间？关账日之后如果需要紧急补录，需要谁批准？ | finance_01_reimbursement_travel_procurement_2026.md | 每月最后一个工作日 18:00；财务经理批准 |
| rag_long_018 | finance_cloud_cost | medium | 云资源成本归集以什么为准？如果未填写项目编码，费用会进入哪里？ | finance_03_budget_cost_marketing_cloud_policy.txt | 项目编码；部门待分摊池 |
| rag_long_019 | it_vpn_account | easy | VPN 访问异常连续失败几次会触发账号保护？员工应该如何恢复，能不能共用他人账号？ | it_01_account_permission_vpn_baseline.md | 连续失败 5 次；通过工单恢复；不得共用他人账号 |
| rag_long_020 | it_secret_policy | easy | 密钥可以写入代码仓库、即时通讯或文档正文吗？公司要求密钥存放在哪里？ | it_03_production_access_secret_db_policy.txt | 不得写入代码仓库、即时通讯或文档正文；公司密钥管理系统 |
| rag_long_021 | it_incident_sla | medium | P1 安全事件的响应时限是什么？请说明响应、建立战情室和初步复盘三个时间要求。 | it_02_incident_response_backup_playbook.docx | 15 分钟内响应；30 分钟内建立战情室；24 小时内完成初步复盘 |
| rag_long_022 | it_db_export | medium | 数据库导出超过 10 万行或包含个人信息时，需要经过哪些审批？ | it_03_production_access_secret_db_policy.txt | 数据 owner；安全团队双审批 |
| rag_long_023 | it_production_access | medium | 生产环境权限默认有效期最长是多少天？续期时必须重新说明哪些内容？ | it_01_account_permission_vpn_baseline.md | 不超过 7 天；业务背景；回滚计划 |
| rag_long_024 | it_offboarding | medium | 离职员工账号在什么时候前禁用？哪些权限或访问需要提前回收？ | it_02_incident_response_backup_playbook.docx | 离职日 18:00 前禁用；生产权限；密钥访问；提前回收 |
| rag_long_025 | product_platform_overview | easy | 企业智能助手平台由哪些核心组成部分构成？ | product_01_agent_platform_overview.md | 知识库检索；工具调用；工作流编排；审计追踪；前端控制台 |
| rag_long_026 | product_rag_eval | medium | RAG 质量评测至少应该包含哪五类指标？ | product_02_rag_quality_eval_guidelines.docx | 命中率；引用准确率；答案忠实度；拒答质量；多轮上下文保持 |
| rag_long_027 | product_tool_safety | medium | 工具调用为什么必须区分只读动作和写入动作？写入动作需要哪些保障？ | product_03_tool_calling_trace_observability.txt | 区分只读动作和写入动作；权限；参数校验；执行后验证 |
| rag_long_028 | product_permission_rag | hard | 知识库权限为什么不能只在回答阶段过滤？检索阶段应该如何处理无权限文档片段？ | product_01_agent_platform_overview.md | 目录级 ACL 与文档级标签组合；检索时不能把无权限文档片段传给模型 |
| rag_long_029 | cross_document_comparison | hard | 比较财务制度里的“审批通过但执行结果与申请不一致”和产品工具调用里的“写入动作执行后验证”：两者共同强调了什么？ | finance_01_reimbursement_travel_procurement_2026.md, product_03_tool_calling_trace_observability.txt | 不能只看审批或工具返回成功；需要留痕；需要执行后验证或补充说明；保证结果与申请一致 |
| rag_long_030 | no_evidence_refusal | medium | 公司 2026 年春节放假从哪一天到哪一天？请给出具体日期和调休安排。 | (无，期望拒答) | 证据不足；无法根据当前知识库给出具体日期和调休安排 |