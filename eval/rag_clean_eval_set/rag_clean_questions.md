# RAG Clean Evaluation Questions

面向已删除污染源后的长文档企业知识库。当前项目可直接读取 `question / expected_sources / should_refuse`。

## rag_clean_001｜public_project_governance｜easy

**Question**：根据《公司运营与协作手册 2026》，2026 年所有跨部门项目在项目主页必须登记哪些信息？

**Expected sources**：public_01_company_operations_handbook_2026.md

**Expected points**：目标; 负责人; 里程碑; 风险状态

**Note**：精确事实；问题中点名目标文档，减少重复条款导致的 source 误判。

## rag_clean_002｜public_formal_portal｜easy

**Question**：根据《公司运营与协作手册 2026》，公司内部统一使用哪个入口作为正式制度入口？飞书或邮件截图能否替代正式制度链接？

**Expected sources**：public_01_company_operations_handbook_2026.md

**Expected points**：星河协同门户; 不能替代正式制度链接

**Note**：测试制度入口和非正式截图边界。

## rag_clean_003｜public_onboarding_process｜medium

**Question**：根据《新员工入职与协作指南 2026》，如果一个申请同时涉及账号、预算和外部供应商支持，应该如何处理？为什么不能放在一个审批结论里？

**Expected sources**：public_02_onboarding_collaboration_guide_2026.docx

**Expected points**：拆成多个任务分别审批; 避免一个审批结论被误用到其他事项; 账号; 预算; 外部供应商支持

**Note**：测试 DOCX 文档、流程拆分和原因解释。

## rag_clean_004｜public_onboarding_traceability｜medium

**Question**：根据《新员工入职与协作指南 2026》，申请人为什么不能只给出口头结论？涉及例外时还要说明哪些内容？

**Expected sources**：public_02_onboarding_collaboration_guide_2026.docx

**Expected points**：填写可验证依据; 不能只给出口头结论; 例外持续时间; 回滚条件; 复核日期

**Note**：测试流程留痕和例外字段。

## rag_clean_005｜public_ai_citation｜medium

**Question**：根据《数据分级、AI 助手使用和引用边界》，涉及 AI 助手的回答为什么必须标注来源？能不能把模型生成内容当作制度原文？

**Expected sources**：public_03_data_classification_ai_usage.txt

**Expected points**：必须标注来源; 不能把模型生成内容当作制度原文; 可追溯; 事实来源

**Note**：测试 TXT 文档和 AI 使用边界。

## rag_clean_006｜public_info_boundary｜medium

**Question**：根据《数据分级、AI 助手使用和引用边界》，公开材料对外分享时有哪些限制？客户名称、报价、源代码和员工个人信息能否放入内部公开材料？

**Expected sources**：public_03_data_classification_ai_usage.txt

**Expected points**：公开材料可以对外分享; 内部公开材料不得包含客户名称、报价、源代码或员工个人信息

**Note**：测试公开/内部公开边界。

## rag_clean_007｜hr_leave_policy｜easy

**Question**：根据《考勤与休假管理制度 2026》，连续病假超过 3 个工作日需要上传什么材料？事假超过 2 天需要哪些审批？

**Expected sources**：hr_01_attendance_leave_policy_2026.md

**Expected points**：医疗证明; 直属负责人; HRBP; 双审批

**Note**：测试 HR 考勤精确事实。

## rag_clean_008｜hr_attendance_hours｜easy

**Question**：根据《考勤与休假管理制度 2026》，标准工时员工每日有效工时按多少小时计算？弹性打卡是否等于免考勤？

**Expected sources**：hr_01_attendance_leave_policy_2026.md

**Expected points**：8 小时; 弹性打卡不等于免考勤

**Note**：测试容易被常识化回答的制度事实。

## rag_clean_009｜hr_performance_appeal｜medium

**Question**：根据《绩效 OKR 与管理者沟通手册》，绩效申诉应在结果发布后多久内提交？逾期提交会不会影响当期结果？

**Expected sources**：hr_02_performance_okr_manager_handbook.docx

**Expected points**：5 个工作日内; 逾期只进入复盘记录; 不影响当期结果

**Note**：测试 DOCX 与时间窗口。

## rag_clean_010｜hr_probation｜medium

**Question**：根据《绩效 OKR 与管理者沟通手册》，试用期转正材料需要包含哪些内容？为什么不能只看直属负责人一句话评价？

**Expected sources**：hr_02_performance_okr_manager_handbook.docx

**Expected points**：目标完成度; 协作反馈; 风险事项; 不能只看直属负责人一句话评价

**Note**：测试多要点回答完整性。

## rag_clean_011｜hr_transfer_boundary｜medium

**Question**：根据《薪酬福利与常见 HR 问答》，员工内部转岗前为什么不能直接调整系统权限？需要先完成什么？

**Expected sources**：hr_03_compensation_benefits_faq.txt

**Expected points**：先完成原岗位交接清单; 未交接完成不得直接调整系统权限

**Note**：测试 HR FAQ 类文档召回。

## rag_clean_012｜hr_exit_process｜medium

**Question**：根据《薪酬福利与常见 HR 问答》，离职流程涉及哪四条线？为什么任一关键项未完成会影响结算？

**Expected sources**：hr_03_compensation_benefits_faq.txt

**Expected points**：薪资; 设备; 账号; 知识交接; 阻塞结算

**Note**：测试列表型事实和解释。

## rag_clean_013｜finance_travel_expense｜easy

**Question**：根据《报销、差旅与采购制度 2026》，单笔差旅报销超过 8000 元时，必须附哪些材料和审批记录？

**Expected sources**：finance_01_reimbursement_travel_procurement_2026.md

**Expected points**：行程单; 发票; 支付凭证; 直属负责人审批记录

**Note**：测试金额阈值和附件列表。

## rag_clean_014｜finance_month_end｜easy

**Question**：根据《报销、差旅与采购制度 2026》，月结关账日是什么时间？关账日之后如果需要紧急补录，需要谁批准？

**Expected sources**：finance_01_reimbursement_travel_procurement_2026.md

**Expected points**：每月最后一个工作日 18:00; 财务经理批准

**Note**：测试时间点和审批人。

## rag_clean_015｜finance_invoice_control｜medium

**Question**：根据《发票、付款、税务和异常入账》，发票抬头、税号、合同主体不一致时，财务是否可以直接入账？应该走什么流程？

**Expected sources**：finance_02_invoice_payment_tax_controls.docx

**Expected points**：不得直接入账; 异常发票处理流程

**Note**：测试异常发票控制。

## rag_clean_016｜finance_supplier_payment｜medium

**Question**：根据《发票、付款、税务和异常入账》，供应商首付款超过合同总额 30% 时，需要哪些复核或确认？

**Expected sources**：finance_02_invoice_payment_tax_controls.docx

**Expected points**：财务复核; 法务确认付款条件

**Note**：测试供应商付款阈值。

## rag_clean_017｜finance_budget_disambiguation｜medium

**Question**：根据《预算、项目成本、市场活动和云资源成本》，市场活动预算是否可以拆单规避审批？累计金额按什么口径合并计算？

**Expected sources**：finance_03_budget_cost_marketing_cloud_policy.txt

**Expected points**：不得拆单规避审批; 同一活动; 同一供应商; 同一自然月

**Note**：测试预算拆单和合并口径。

## rag_clean_018｜finance_cloud_cost｜medium

**Question**：根据《预算、项目成本、市场活动和云资源成本》，云资源成本归集以什么为准？如果未填写项目编码，费用会进入哪里？

**Expected sources**：finance_03_budget_cost_marketing_cloud_policy.txt

**Expected points**：项目编码; 部门待分摊池

**Note**：测试成本归集规则。

## rag_clean_019｜it_vpn_account｜easy

**Question**：根据《账号、权限、VPN 与终端基线》，VPN 访问异常连续失败几次会触发账号保护？员工应该如何恢复？能不能共用他人账号？

**Expected sources**：it_01_account_permission_vpn_baseline.md

**Expected points**：连续失败 5 次; 通过工单恢复; 不得共用他人账号

**Note**：测试 IT 基线精确事实。

## rag_clean_020｜it_production_access｜medium

**Question**：根据《账号、权限、VPN 与终端基线》，生产环境权限默认有效期最长是多少天？续期时必须重新说明哪些内容？

**Expected sources**：it_01_account_permission_vpn_baseline.md

**Expected points**：不超过 7 天; 业务背景; 回滚计划

**Note**：测试生产权限有效期。

## rag_clean_021｜it_incident_sla｜medium

**Question**：根据《安全事件、备份恢复和复盘机制》，P1 安全事件的响应时限是什么？请说明响应、建立战情室和初步复盘三个时间要求。

**Expected sources**：it_02_incident_response_backup_playbook.docx

**Expected points**：15 分钟内响应; 30 分钟内建立战情室; 24 小时内完成初步复盘

**Note**：测试多时间点。

## rag_clean_022｜it_offboarding｜medium

**Question**：根据《安全事件、备份恢复和复盘机制》，离职员工账号在什么时候前禁用？哪些权限或访问需要提前回收？

**Expected sources**：it_02_incident_response_backup_playbook.docx

**Expected points**：离职日 18:00 前禁用; 生产权限; 密钥访问; 提前回收

**Note**：测试离职账号和高风险权限回收。

## rag_clean_023｜it_secret_policy｜easy

**Question**：根据《生产访问、密钥、数据库和导出审批》，密钥可以写入代码仓库、即时通讯或文档正文吗？公司要求密钥存放在哪里？

**Expected sources**：it_03_production_access_secret_db_policy.txt

**Expected points**：不得写入代码仓库、即时通讯或文档正文; 公司密钥管理系统

**Note**：测试安全制度。

## rag_clean_024｜it_db_export｜medium

**Question**：根据《生产访问、密钥、数据库和导出审批》，数据库导出超过 10 万行或包含个人信息时，需要经过哪些审批？

**Expected sources**：it_03_production_access_secret_db_policy.txt

**Expected points**：数据 owner; 安全团队; 双审批

**Note**：测试数据库导出审批。

## rag_clean_025｜product_platform_overview｜easy

**Question**：根据《企业智能助手平台总览》，企业智能助手平台由哪些核心组成部分构成？

**Expected sources**：product_01_agent_platform_overview.md

**Expected points**：知识库检索; 工具调用; 工作流编排; 审计追踪; 前端控制台

**Note**：测试产品总览模块列表。

## rag_clean_026｜product_permission_rag｜hard

**Question**：根据《企业智能助手平台总览》，知识库权限为什么不能只在回答阶段过滤？检索阶段应该如何处理无权限文档片段？

**Expected sources**：product_01_agent_platform_overview.md

**Expected points**：目录级 ACL; 文档级标签; 检索时不能把无权限文档片段传给模型

**Note**：测试权限过滤发生在检索阶段。

## rag_clean_027｜product_rag_eval｜medium

**Question**：根据《RAG 质量评测指南》，RAG 质量评测至少应该包含哪五类指标？

**Expected sources**：product_02_rag_quality_eval_guidelines.docx

**Expected points**：命中率; 引用准确率; 答案忠实度; 拒答质量; 多轮上下文保持

**Note**：测试评测指南 DOCX。

## rag_clean_028｜product_rag_citation｜medium

**Question**：根据《RAG 质量评测指南》，RAG 系统回答为什么必须引用事实来源？为什么不应把历史示例中的结论直接套用到当前问题？

**Expected sources**：product_02_rag_quality_eval_guidelines.docx

**Expected points**：引用事实来源; 不应把历史示例中的结论直接套用到当前问题; 事实确认; 判断建议

**Note**：测试引用忠实度和历史示例边界。

## rag_clean_029｜product_tool_safety｜medium

**Question**：根据《工具调用、Trace、可观测性和回答生成》，工具调用为什么必须区分只读动作和写入动作？写入动作需要哪些保障？

**Expected sources**：product_03_tool_calling_trace_observability.txt

**Expected points**：区分只读动作和写入动作; 权限; 参数校验; 执行后验证

**Note**：测试工具调用治理。

## rag_clean_030｜product_trace_validation｜medium

**Question**：根据《工具调用、Trace、可观测性和回答生成》，如果写入型工具调用失败，为什么不能只根据工具返回 ok 就回答成功？

**Expected sources**：product_03_tool_calling_trace_observability.txt

**Expected points**：写入动作; 执行后验证; 不能只根据工具返回 ok; 结果与申请一致

**Note**：测试执行后验证和回答忠实度。

## rag_clean_031｜no_evidence_refusal｜medium

**Question**：公司 2026 年春节放假从哪一天到哪一天？请给出具体日期和调休安排。

**Expected sources**：(none / should refuse)

**Expected points**：证据不足; 无法根据当前知识库给出具体日期和调休安排

**Note**：测试无证据拒答；不要用常识或外部假期安排编造。

## rag_clean_032｜no_evidence_refusal｜medium

**Question**：公司是否提供海外长期派驻补贴？如果提供，补贴金额、申请周期和税务处理分别是什么？

**Expected sources**：(none / should refuse)

**Expected points**：证据不足; 当前知识库没有海外长期派驻补贴金额、申请周期和税务处理

**Note**：测试 HR/Finance 交叉但无依据场景。
