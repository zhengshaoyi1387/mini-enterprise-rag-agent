# Interview Guide：字节 Agent 开发面试讲法

## 1. 1 分钟项目介绍

我做了一个面向企业知识库的 Agentic RAG Infra Mini System。它基于 LangGraph 把一次问答拆成上下文加载、问题理解、路由、检索规划、混合检索、证据反思、答案生成和上下文持久化等节点。检索链路支持 Chroma 向量检索、BM25、RRF 融合和 Qwen rerank。工程化方面，我把它封装成 FastAPI 服务，新增 `/chat`、`/traces/{trace_id}`、API Key 鉴权、角色权限、工具权限和 trace 可观测能力。

## 2. 3 分钟架构介绍

从请求进入 `/chat` 开始，API Gateway 会先校验 `X-API-Key`，读取 `user_id` 和 `role`，生成 `trace_id`，做接口权限和轻量安全检查。然后请求进入 LangGraph Agent。Agent 先读取会话上下文，把追问改写为独立问题，再由 Router 判断走 direct、rag、tool 还是 reject。需要检索时，Retrieval Planner 生成一个或多个 search task，检索层用向量召回和 BM25 召回，再用 RRF 融合、rerank 精排。检索后 Evidence Reflector 判断证据是否足够，不足则补检索或拒答。最后模型只基于证据生成带引用答案，并把节点耗时、工具调用和来源写入 trace。

## 3. 高频追问与回答

### Q1：为什么用 LangGraph，而不是普通 RAG Chain？

普通 RAG Chain 是固定流程，每个问题都检索再回答。企业知识库场景的问题类型不同，有些可以直接回答，有些需要检索，有些要拒答，有些需要多 query 检索和证据反思。LangGraph 能把这些步骤显式节点化，方便做路由、循环控制、trace 和失败定位。

### Q2：BM25、向量检索、RRF、rerank 分别解决什么？

向量检索擅长语义相似，BM25 擅长制度名、产品名、字段名等关键词精确匹配。两者分数体系不同，所以用 RRF 做无监督融合。rerank 则在候选集合上重新判断 query-document 相关性，把最终给模型的证据质量提高。

### Q3：证据不足怎么办？

我有 Evidence Reflector 节点，它会判断当前证据是否足够。如果不足，会生成 followup search task 继续检索；如果达到最大反思轮次还不足，最终回答会说明当前知识库证据不足，而不是无证据编造。

### Q4：怎么防止越权工具调用？

我做了两层权限。API Gateway 检查 endpoint permission，比如 trace 只有 admin 能看。工具执行前再检查 tool permission，比如 search_knowledge_base 对 guest 开放，但 compare_sources 需要 user/admin，run_eval 只有 admin。安全边界在程序侧，不依赖 prompt。

### Q5：trace_id 有什么用？

trace_id 把一次请求中的 API、Router、检索、工具调用、证据反思和最终回答串起来。出现回答错误或延迟高时，我可以通过 `/traces/{trace_id}` 看每个节点耗时、route、检索 query、召回数量、来源和错误位置。

## 4. 当前项目亮点

- LangGraph 状态机，而不是普通 chain。
- 混合检索 + RRF + rerank。
- LLM Router + Retrieval Planner + Evidence Reflector。
- FastAPI Gateway 服务化。
- API Key 鉴权 + role 权限。
- 工具执行前程序侧权限检查。
- trace_id + `/traces/{trace_id}` 可观测接口。
- SQLite 多轮上下文。

## 5. 下一阶段可继续优化

- retrieval ablation：vector-only vs hybrid vs hybrid+rerank。
- 扩充 eval questions 到 30-50 条。
- `/chat/stream` SSE 流式输出。
- `/eval/run` 管理接口。
- Docker Compose 一键启动。
