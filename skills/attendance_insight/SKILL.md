# attendance_insight

## 适用场景

用于对指定日期范围内的考勤记录做**统计分析和洞察分析**，不是简单查询明细。适合回答：

- 上周考勤异常整体情况如何？
- 哪些员工迟到、缺勤或请假异常最多？
- 哪些部门异常更集中？
- 是否存在重复迟到、混合异常、部门集中异常等模式？
- 给 HR 输出一份考勤异常周报摘要。

## 与普通 Tool 的区别

`query_attendance_summary` 负责查询原始记录、明细和基础分组统计。

`attendance_insight` 负责基于结构化考勤数据生成领域洞察，包括：总览、排行、模式识别、风险提示和后续建议。

## 不适用场景

- 不修改考勤记录。
- 不审批请假。
- 不查询原始明细；明细应走 `query_attendance_summary`。
- 不回答制度原文，制度解释应继续走 RAG。

## 输入

- `start_date`: 开始日期，格式 `YYYY-MM-DD`。
- `end_date`: 结束日期，格式 `YYYY-MM-DD`。
- `group_by`: 可选，`employee`、`department` 或 `status`。
- `include_normal`: 可选，是否在分组明细中保留正常出勤统计。

## 输出

返回结构化 JSON，包括：

- `overview`: 总记录数、异常记录数、异常员工数、异常部门数、异常率。
- `items`: 与旧版本兼容的分组聚合结果。
- `rankings`: 异常员工排行、迟到排行、缺勤排行、部门异常排行。
- `patterns`: 重复迟到、重复缺勤、混合异常、部门集中异常。
- `risk_flags`: 基于固定规则生成的低/中/高风险提示。
- `suggested_followups`: 可继续追问的问题。
- `limitations`: 数据来源和能力边界说明。

异常口径固定为：`late`、`leave`、`absent`。`present` 属于正常出勤。

## 失败策略

如果输入缺少日期、数据库不可访问或输出不符合 schema，返回结构化错误，由 SkillExecutor 包装为失败结果。
