from __future__ import annotations

from mini_rag.agent.graph_agent import EnterpriseKnowledgeGraphAgent
from mini_rag.agent.legacy_agent import LegacyEnterpriseKnowledgeAgent
from mini_rag.config import Settings


class EnterpriseKnowledgeAgent:
    """统一 Agent 入口。

    默认 `AGENT_RUNTIME=langgraph`，使用 LangGraph 状态机 Agent。
    如果需要对比旧版脚本式 Agent，可在 `.env` 中设置 `AGENT_RUNTIME=legacy`。
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        # 这个 wrapper 的作用是保持 API/CLI 不变：
        # 外部仍然 import EnterpriseKnowledgeAgent，但内部可以根据配置切换实现。
        # - langgraph：新的状态机工作流。
        # - legacy：旧的 create_agent 脚本式 Agent，用于学习对比或回退。
        if settings.agent_runtime == "legacy":
            self._impl = LegacyEnterpriseKnowledgeAgent(settings)
        else:
            self._impl = EnterpriseKnowledgeGraphAgent(settings)

    def ask(
        self,
        question: str,
        session_id: str | None = None,
        retrieval_mode: str | None = None,
        enable_rerank: bool | None = None,
        user_id: str | None = None,
        role: str | None = None,
        trace_id: str | None = None,
        kb_ids: list[str] | None = None,
    ) -> dict:
        """把 ask 调用转发给当前 runtime 的具体实现。

        ``user_id``、``role``、``trace_id`` 是服务化接口新增的请求级元数据。
        CLI/旧 /query 不传这些字段时会自动使用安全默认值，保持向后兼容。
        """
        return self._impl.ask(
            question,
            session_id=session_id,
            retrieval_mode=retrieval_mode,
            enable_rerank=enable_rerank,
            user_id=user_id,
            role=role,
            trace_id=trace_id,
            kb_ids=kb_ids,
        )

    def stream(
        self,
        question: str,
        session_id: str | None = None,
        retrieval_mode: str | None = None,
        enable_rerank: bool | None = None,
        user_id: str | None = None,
        role: str | None = None,
        trace_id: str | None = None,
        kb_ids: list[str] | None = None,
    ):
        if hasattr(self._impl, "stream"):
            yield from self._impl.stream(
                question,
                session_id=session_id,
                retrieval_mode=retrieval_mode,
                enable_rerank=enable_rerank,
                user_id=user_id,
                role=role,
                trace_id=trace_id,
                kb_ids=kb_ids,
            )
            return
        result = self.ask(
            question,
            session_id=session_id,
            retrieval_mode=retrieval_mode,
            enable_rerank=enable_rerank,
            user_id=user_id,
            role=role,
            trace_id=trace_id,
            kb_ids=kb_ids,
        )
        answer = result.get("answer", "")
        if answer:
            yield {"event": "token", "content": answer}
        yield {"event": "final", "answer": answer, "route": result.get("route"), "sources": result.get("sources", []), "trace": result.get("trace", {})}
