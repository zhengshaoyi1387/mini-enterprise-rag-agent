# Agent Evaluation Suite Report

- Generated at: `2026-05-17T15:39:00.295735+00:00`
- Suite: `rag`
- Judge: `rule`
- Mode: `hybrid`

## Summary

| Scope | Cases | Passed | Failed | Pass Rate | Avg Latency(ms) | P95 Latency(ms) |
|---|---:|---:|---:|---:|---:|---:|
| overall | 32 | 27 | 5 | 0.8438 | 9717.87 | 14380.54 |
| rag | 32 | 27 | 5 | 0.8438 | 9717.87 | 14380.54 |

## Metrics By Suite

### rag

| Metric | Value |
|---|---:|
| total_cases | 32 |
| executed_cases | 32 |
| infra_error_cases | 0 |
| agent_passed_cases | 27 |
| agent_failed_cases | 5 |
| agent_pass_rate | 0.8438 |
| case_count | 32 |
| passed | 27 |
| failed | 5 |
| pass_rate | 0.8438 |
| avg_latency_ms | 9717.87 |
| p95_latency_ms | 14380.54 |
| citation_hit | 1.0 |
| recall_at_k_hit | 1.0 |
| refusal_hit | 0.8438 |

## Failed Cases

### rag / rag_clean_019

- Question: 根据《账号、权限、VPN 与终端基线》，VPN 访问异常连续失败几次会触发账号保护？员工应该如何恢复？能不能共用他人账号？
- Failure reasons: refusal behavior mismatch
- Retrieved sources: it/it_01_account_permission_vpn_baseline.md
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 根据《账号、权限、VPN 与终端基线》的规定：

1. **触发账号保护的条件**：当员工通过VPN访问时，如果连续失败5次，将会触发账号保护机制。
2. **恢复方式**：遇到这种情况后，员工需要提交工单来恢复其账号的正常使用。
3. **共用账号规定**：明确规定不允许员工之间共用账号。

以上信息基于提供的文档内容总结得出。对于更具体的流程细节或特殊情况处理，请参考公司内部指南或联系IT服务台获取帮助。

来源：
- source: it/it_01_account_permission_vpn_baseline.md
- title_path: 账号、权限、VPN 与终端基线 > 6. 场景案例 > 案例 10：账号权限、VPN、终端和安全基线的边界判断
- chunk_id: 5a16f46f95dd:chunk:0102:82248773
- title_path: 账号、权限、VPN 与终端基线 > 4. 关键规则与阈值
- chunk_id: 5a16f46f95dd:chunk:0087:3c2c6d92

### rag / rag_clean_020

- Question: 根据《账号、权限、VPN 与终端基线》，生产环境权限默认有效期最长是多少天？续期时必须重新说明哪些内容？
- Failure reasons: refusal behavior mismatch
- Retrieved sources: it/it_01_account_permission_vpn_baseline.md
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 根据《账号、权限、VPN 与终端基线》的规定，生产环境权限默认有效期最长为7天。续期时必须重新说明业务背景和回滚计划。

引用来源：
- source: it/it_01_account_permission_vpn_baseline.md
- title_path: 账号、权限、VPN 与终端基线 > 4. 关键规则与阈值
- chunk_id: 5a16f46f95dd:chunk:0091:e9352131

### rag / rag_clean_026

- Question: 根据《企业智能助手平台总览》，知识库权限为什么不能只在回答阶段过滤？检索阶段应该如何处理无权限文档片段？
- Failure reasons: refusal behavior mismatch
- Retrieved sources: product/product_01_agent_platform_overview.md
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 根据提供的证据，知识库权限不能只在回答阶段过滤的原因是需要确保无权限文档片段不会被传给模型。这表明，在检索阶段就应当进行权限控制，以避免将用户无权访问的信息纳入考虑范围。具体做法是在检索过程中应用目录级 ACL（访问控制列表）与文档级标签组合的方式，来排除那些用户没有权限查看的文档片段。

来源：
- source: product/product_01_agent_platform_overview.md
- title_path: 企业智能助手平台总览 > 6. 场景案例 > 案例 6：企业智能助手平台、模块边界和版本范围的边界判断
- chunk_id: 63818fb1e478:chunk:0131:843e11aa

- source: product/product_01_agent_platform_overview.md
- title_path: 企业智能助手平台总览 > 3. 标准流程
- chunk_id: 63818fb1e478:chunk:0118:b6dffc49

- source: product/product_01_agent_platform_overview.md
- title_path: 企业智能助手平台总览 > 7. FAQ
- chunk_id: 63818fb1e478:chunk:0136:e6991a54

### rag / rag_clean_031

- Question: 公司 2026 年春节放假从哪一天到哪一天？请给出具体日期和调休安排。
- Failure reasons: refusal behavior mismatch
- Retrieved sources: hr/hr_01_attendance_leave_policy_2026.md, public/public_01_company_operations_handbook_2026.md, finance/finance_01_reimbursement_travel_procurement_2026.md
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 根据现有提供的证据，没有找到关于2026年春节具体放假日期及调休安排的信息。因此，无法直接回答您的问题。

为了获取准确的放假信息，建议您查看公司发布的最新通知或联系人力资源部门确认具体的放假安排。

【引用来源】
- source: hr/hr_01_attendance_leave_policy_2026.md, title_path: 考勤与休假管理制度 2026, chunk_id: ec54b0e8c9bd:chunk:0040:8f594ef7
- source: public/public_01_company_operations_handbook_2026.md, title_path: 公司运营与协作手册 2026 > 7. FAQ, chunk_id: 12a3cac20f2f:chunk:0169:4d085d89
- source: finance/finance_01_reimbursement_travel_procurement_2026.md, title_path: 报销、差旅与采购制度 2026, chunk_id: 610f384d361e:chunk:0007:edc81744

### rag / rag_clean_032

- Question: 公司是否提供海外长期派驻补贴？如果提供，补贴金额、申请周期和税务处理分别是什么？
- Failure reasons: refusal behavior mismatch
- Retrieved sources: hr/hr_03_compensation_benefits_faq.txt
- Tool calls: `[]`
- Task results: `[]`
- Answer preview: 根据目前提供的信息，没有直接提到公司是否提供海外长期派驻补贴，以及具体的补贴金额、申请周期和税务处理方式。上述证据主要讨论了薪酬福利、补贴等事项在人力资源部执行时的一般原则和流程，并未具体涉及海外长期派驻的相关政策。

为了获取更准确的信息，请查阅有关海外派驻的具体政策文件或联系人力资源部门进行咨询。

**引用来源：**
- source: hr/hr_03_compensation_benefits_faq.txt
- title_path: hr_03_compensation_benefits_faq.txt
- chunk_id: d9436d4dd08b:chunk:0201:1934b71f, d9436d4dd08b:chunk:0204:e71c48a7, d9436d4dd08b:chunk:0196:72f1eebe
