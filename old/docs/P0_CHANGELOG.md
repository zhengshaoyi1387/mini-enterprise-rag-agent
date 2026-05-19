# P0 Changelog

## 已完成

1. 新增 `src/mini_rag/api/schemas.py`
   - `ChatRequest`
   - `ChatResponse`
   - `TraceResponse`

2. 新增 `src/mini_rag/api/dependencies.py`
   - `verify_api_key`
   - `get_request_role`

3. 新增 `src/mini_rag/security/permissions.py`
   - endpoint permission
   - tool permission
   - role normalize
   - program-side permission assert

4. 新增 `src/mini_rag/security/safety.py`
   - 轻量危险关键词拒答

5. 新增 `src/mini_rag/observability/trace_store.py`
   - trace 文件查找
   - retrieval_trace 提取
   - readable trace 构造

6. 改造 `src/mini_rag/api/app.py`
   - 保留 `/query`
   - 新增 `/chat`
   - 新增 `/traces/{trace_id}`
   - Agent/RAG 懒加载单例
   - trace_id 生成与保存

7. 改造 LangGraph workflow
   - `user_id`、`role`、`trace_id` 注入 state
   - build_trace 输出请求级元数据
   - retrieve 节点执行前检查 `search_knowledge_base` 权限

8. 新增测试
   - `tests/test_api_auth.py`
   - `tests/test_permissions.py`
   - `tests/test_trace_store.py`

9. 新增文档
   - `ARCHITECTURE.md`
   - `SECURITY.md`
   - `INTERVIEW_GUIDE.md`
   - `API_TESTING.md`

## 暂未完成

- Docker / docker-compose：按你的要求本阶段先不做。
- retrieval ablation：属于 P1。
- `/chat/stream`：属于 P2。
