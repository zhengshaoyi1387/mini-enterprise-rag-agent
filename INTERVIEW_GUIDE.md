# Interview Guide：字节 Agent 开发面试讲法

## 1. 1 分钟项目介绍

我做了一个面向企业知识库和企业日常助手的 Agentic RAG Infra Mini System。它基于 LangGraph 把一次问答拆成上下文加载、权限感知能力目录、多任务 Planner、显式 RAG/tool 分支执行、完成度反思、最终答案生成和上下文持久化等节点。检索链路支持 Chroma 向量检索、BM25、RRF 融合和 Qwen rerank。工具层不堆砌 mock prompt wrapper，只保留知识库检索、当前时间、CSV 考勤统计和 JSON 公司日程这几类真实边界工具。工程化方面，我把它封装成 FastAPI 服务，新增 `/chat`、`/traces/{trace_id}`、登录会话、角色权限、工具权限和 trace 可观测能力。

## 2. 3 分钟架构介绍

从请求进入 `/chat` 开始，API Gateway 从 Bearer token 解析当前用户和角色，生成 `trace_id`，做接口权限和轻量安全检查。然后请求进入 LangGraph Agent。Agent 先读取会话上下文和上一轮 `previous_tool_context`，再由 ToolRegistry 生成当前角色可见的 capability catalog。LLM Planner 只能基于这个目录输出严格 JSON `execution_plan.tasks[]`，每个 task 都有 kind、objective、tool/action/input、time_requirement 和 depends_on。Planner 输出后，程序侧做 contract normalizer，修正 `route` 与 task 的结构化冲突，并清理 smalltalk、权限不足、拒答这类 direct-only 消息里的工具字段。相对日期不靠上下文继承，也不让模型猜当前日期；只要任务声明需要当前日期，执行层就内部调用 `get_current_datetime`，再按工具 action schema 补齐 query 的 `start_date/end_date` 或写操作的 `date`。制度、流程、FAQ 走 RAG；考勤统计走 CSV 工具；公司会议、培训、发薪日等走 JSON 日程工具。任务执行完成后，`completion_reflect` 会检查原始请求的所有子目标是否完成；复杂问题如果漏了子任务，会补 task 再执行，最后由回答 LLM 综合 task_results、证据和工具结果生成最终回答。

## 3. 高频追问与回答

### Q1：为什么用 LangGraph，而不是普通 RAG Chain？

普通 RAG Chain 是固定流程，每个问题都检索再回答。企业知识库场景的问题类型不同，有些可以直接回答，有些需要检索，有些要拒答，有些需要多个 RAG/tool 子任务和最终完成度反思。LangGraph 能把这些步骤显式节点化，方便做路由、循环控制、trace 和失败定位。

### Q2：BM25、向量检索、RRF、rerank 分别解决什么？

向量检索擅长语义相似，BM25 擅长制度名、产品名、字段名等关键词精确匹配。两者分数体系不同，所以用 RRF 做无监督融合。rerank 则在候选集合上重新判断 query-document 相关性，把最终给模型的证据质量提高。

### Q3：证据不足怎么办？

我把默认主流程收敛为最终答案前的单一 `completion_reflect`。它不只看证据够不够，还会对照用户原始请求和 `execution_plan`，判断所有 RAG / tool 子目标是否都完成。如果发现只完成了一半，就补执行缺失 task；如果达到补救上限仍不完整，最终回答会说明哪部分缺少证据或执行失败，而不是无证据编造。旧的 RAG 证据评估能力只作为兼容函数保留，不再是默认图里的独立节点。

### Q4：怎么防止越权工具调用？

我做了三层权限。API Gateway 检查 endpoint permission，比如 trace 和管理接口只有 admin 能看。Planner 之前先生成 permission-aware capability catalog，模型只能看到当前角色允许的工具和 action，比如员工只看到 `manage_company_calendar.query`，看不到 create/update/delete。工具执行前再做 `assert_tool_action_permission`，即使模型被诱导输出越权 action，也会被程序侧拦截。安全边界不依赖 prompt。

### Q5：trace_id 有什么用？

trace_id 把一次请求中的 API、Planner、检索、工具调用、完成度反思和最终回答串起来。出现回答错误或延迟高时，我可以通过 `/traces/{trace_id}` 看每个节点耗时、route、检索 query、召回数量、来源和错误位置。

### Q6：为什么不直接用关键词规则调用工具？

关键词规则只能判断“可能是什么工具”，但不能稳定规划参数，也处理不好权限、action 和复合任务。比如 public 用户问公司日程时，Planner 根本不应该看到日程工具；员工问新增日程时，Planner 只能看到 query action，所以应输出 `permission_required`。因此我取消了关键词主路由，用权限过滤后的工具目录约束 LLM `execution_plan`；代码层再负责 Planner contract 归一化、action-level RBAC、日期解析、Schema 校验、任务执行和完成度反思。

## 4. 当前项目亮点

- LangGraph 状态机，而不是普通 chain。
- 混合检索 + RRF + rerank。
- Permission-aware Multi-task Planner + Retrieval Planner + Completion Reflector。
- Permission-aware Tool Catalog：Planner 只看到当前角色允许的工具和 action。
- LLM Execution Planning：LLM 产出 message_type、context_usage 和覆盖所有子目标的 `execution_plan.tasks[]`。
- Planner Contract Normalizer：修正 route/task/tool/action 字段冲突，避免多轮追问跳过工具。
- Current Datetime Resolver：相对日期永远调用当前时间工具解析，不继承上一轮日期，不让模型猜当前日期。
- Completion Reflector：最终回答前检查所有 RAG / tool 子目标是否完成，必要时补 task。
- FastAPI Gateway 服务化。
- 登录会话 + role 权限。
- 工具执行前程序侧权限检查。
- 少量真实企业工具：知识库检索、当前时间、CSV 考勤、JSON 日程。
- trace_id + `/traces/{trace_id}` 可观测接口，trace 中保存 current_tool_context 以支持多轮追问。
- SQLite 多轮上下文。

## 5. 下一阶段可继续优化

- retrieval ablation：vector-only vs hybrid vs hybrid+rerank。
- 扩充 eval questions 到 30-50 条。
- `/chat/stream` SSE 流式输出。
- `/eval/run` 管理接口。
- Docker Compose 一键启动。
