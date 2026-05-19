from __future__ import annotations

from mini_rag.agent.graph_agent import EnterpriseKnowledgeGraphAgent
from mini_rag.config import Settings


class EnterpriseKnowledgeAgent:
    """统一 Agent 入口。

    当前主线固定使用 LangGraph 状态机 Agent。旧版脚本式 Agent 已归档到
    ``old/``，不再作为运行时分支暴露，避免面试展示时出现两套心智模型。
    """

    def __init__(self, settings: Settings):
        self.settings = settings
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
        override_now: str | None = None,
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
            override_now=override_now,
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
        override_now: str | None = None,
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
                override_now=override_now,
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
            override_now=override_now,
        )
        answer = result.get("answer", "")
        if answer:
            yield {"event": "token", "content": answer}
        yield {"event": "final", "answer": answer, "route": result.get("route"), "sources": result.get("sources", []), "trace": result.get("trace", {})}
