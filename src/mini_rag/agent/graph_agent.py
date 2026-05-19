from __future__ import annotations

from mini_rag.config import Settings
from mini_rag.graph.workflow import AgenticRAGWorkflow


class EnterpriseKnowledgeGraphAgent:
    """基于 LangGraph 的 Agentic RAG 实现。

    这是重构后的主实现：
    - LLM 负责上下文理解、路由、检索规划、证据反思、最终生成。
    - LangGraph 负责状态流转、循环控制和单轮运行状态隔离。
    - SQLiteContextStore 只保存业务会话记忆，不保存 LangGraph runtime state。
    """

    def __init__(self, settings: Settings, llm=None, retriever=None, context_store=None):
        self.settings = settings
        self.workflow = AgenticRAGWorkflow(settings, llm=llm, retriever=retriever, context_store=context_store)

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
        state = self.workflow.run(
            question=question,
            session_id=session_id,
            retrieval_mode=retrieval_mode,
            enable_rerank=enable_rerank,
            user_id=user_id,
            role=role,
            trace_id=trace_id,
            kb_ids=kb_ids,
            override_now=override_now,
        )
        trace = self.workflow.nodes.build_trace(state)
        return {
            "answer": state.get("final_answer", ""),
            "route": state.get("route", ""),
            "sources": state.get("sources", []),
            "mainline_log": state.get("mainline_log", []),
            "mainline_log_text": state.get("mainline_log_text", ""),
            "trace": trace,
        }

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
        yield from self.workflow.stream(
            question=question,
            session_id=session_id,
            retrieval_mode=retrieval_mode,
            enable_rerank=enable_rerank,
            user_id=user_id,
            role=role,
            trace_id=trace_id,
            kb_ids=kb_ids,
            override_now=override_now,
        )


def build_readable_steps(trace: dict) -> list[dict]:
    """把 trace 转成适合前端/文档展示的步骤列表。

    这是面向前端/文档展示的小工具；完整 trace 字段会原样留在 trace JSON 中。
    """
    steps: list[dict] = []
    observations = trace.get("observations") or []
    tool_observation = next((item for item in observations if item.get("type") == "tool"), {})
    retrieval_trace = tool_observation.get("retrieval_trace") or {}

    for item in trace.get("node_trace", []):
        node = item.get("node", "")
        step = {
            "node": node,
            "latency_ms": item.get("latency_ms"),
            "error": item.get("error"),
            "input": {},
            "output": {},
        }
        if node in {"build_runtime_context", "manage_context"}:
            step["input"] = {"session_id": trace.get("session_id")}
            context_events = trace.get("context_events") or []
            event = next((event for event in context_events if event.get("node") == node), {})
            step["output"] = event
        elif node in {"route", "llm_router"}:
            step["input"] = {"question": trace.get("question"), "standalone_query": trace.get("standalone_query")}
            step["output"] = {
                "route": trace.get("route"),
                "risk_level": trace.get("risk_level"),
                "reason": trace.get("router_reason"),
            }
        elif node in {"react_execute", "execute_tool"}:
            step["input"] = {"tool_calls": trace.get("tool_calls", [])}
            step["output"] = {
                "tool_name": tool_observation.get("tool_name"),
                "retrieval_engine": retrieval_trace.get("retrieval_engine"),
                "result_count": retrieval_trace.get("result_count"),
                "retrieved_sources": retrieval_trace.get("results") or trace.get("sources", []),
            }
        elif node in {"answer_with_llm", "final"}:
            step["input"] = {"source_count": len(trace.get("sources") or [])}
            step["output"] = {"answer": trace.get("answer")}
        else:
            step["output"] = {key: item.get(key) for key in ("route", "output_keys") if key in item}
        steps.append(step)
    return steps
