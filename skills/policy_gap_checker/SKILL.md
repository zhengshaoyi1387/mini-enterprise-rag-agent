# policy_gap_checker

## 适用场景

用于检查 RAG 已检索到的 evidence 是否覆盖用户问题中的关键槽位，例如“是否可报销”“所需材料”“审批流程”“申请入口”“处理时限”等。

## 边界

- 不直接生成制度结论。
- 不替代 RAG Evidence Judge。
- 不把 related evidence 或 candidate evidence 变成 supporting evidence。
- 只基于输入的 `evidence_items` 做覆盖分析。
- `partial` 表示证据有相关信号，但仍不足以直接支持完整回答。

## 输入

- `question`: 当前子任务问题，而不是整个原始多任务问题。
- `evidence_items`: 已确认可用于分析的相关证据片段。
- `required_slots`: 需要检查的槽位列表。

## 输出

- `covered_slots`: 完整覆盖槽位，`coverage_level=full`。
- `partial_slots`: 部分覆盖槽位，`coverage_level=partial`。
- `missing_slots`: 未覆盖槽位，`coverage_level=missing`。
- `overall`: `full`、`partial` 或 `none`。
- `limitations`: 固定限制说明。

## 覆盖口径

- 证据提到“行程单、发票、支付凭证”等，只能说明材料槽位至少部分覆盖，不代表“酒店费用可以报销”。
- 证据提到“直属负责人审批记录”，审批流程只能判为 partial；只有出现多个流程节点或明确流转步骤，才判 full。
- 是否允许/是否可报销必须有明确结论性表达，不能由材料要求反推。
