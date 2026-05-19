from __future__ import annotations

from typing import Any

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state
from mini_rag.graph.state import AgentState


class AgenticRAGWorkflow:
    """LangGraph workflow for the enterprise Agent.

    Main graph:
    build_runtime_context -> plan_with_llm -> resolve_plan_time ->
    validate_plan -> react_execute -> answer_with_llm -> update_memory -> END
    """

    def __init__(self, settings: Settings, llm: Any | None = None, retriever: Any | None = None, context_store: Any | None = None):
        self.settings = settings
        self.nodes = AgenticRAGNodes(settings, llm=llm, retriever=retriever)
        if context_store is not None:
            self.nodes.context_store = context_store
        self._compiled = self._build_langgraph()

    def run(
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
    ) -> AgentState:
        state = create_initial_state(
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
        if self._compiled is not None:
            config = {"configurable": {"thread_id": state["workflow_run_id"]}}
            return self._compiled.invoke(state, config=config)
        return self._run_fallback(state)

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
        state = create_initial_state(
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
        state = self._run_until_generate(state)
        for token in self.nodes.stream_generate_answer(state):
            if token:
                yield {"event": "token", "content": token}
        state = self.nodes.update_memory(state)
        trace = self.nodes.build_trace(state)
        yield {
            "event": "final",
            "answer": state.get("final_answer", ""),
            "route": state.get("route", ""),
            "sources": state.get("sources", []),
            "trace": trace,
        }

    def _build_langgraph(self) -> Any | None:
        try:
            from langgraph.graph import END, StateGraph
        except Exception:
            return None

        workflow = StateGraph(AgentState)
        workflow.add_node("build_runtime_context", self.nodes.build_runtime_context)
        workflow.add_node("plan_with_llm", self.nodes.plan_with_llm)
        workflow.add_node("resolve_plan_time", self.nodes.resolve_plan_time)
        workflow.add_node("validate_plan", self.nodes.validate_plan)
        workflow.add_node("react_execute", self.nodes.react_execute)
        workflow.add_node("answer_with_llm", self.nodes.answer_with_llm)
        workflow.add_node("update_memory", self.nodes.update_memory)

        workflow.set_entry_point("build_runtime_context")
        workflow.add_edge("build_runtime_context", "plan_with_llm")
        workflow.add_edge("plan_with_llm", "resolve_plan_time")
        workflow.add_edge("resolve_plan_time", "validate_plan")
        workflow.add_edge("validate_plan", "react_execute")
        workflow.add_edge("react_execute", "answer_with_llm")
        workflow.add_edge("answer_with_llm", "update_memory")
        workflow.add_edge("update_memory", END)
        return workflow.compile()

    def _run_fallback(self, state: AgentState) -> AgentState:
        state = self._run_until_generate(state)
        state = self.nodes.answer_with_llm(state)
        state = self.nodes.update_memory(state)
        return state

    def _run_until_generate(self, state: AgentState) -> AgentState:
        state = self.nodes.build_runtime_context(state)
        state = self.nodes.plan_with_llm(state)
        state = self.nodes.resolve_plan_time(state)
        state = self.nodes.validate_plan(state)
        state = self.nodes.react_execute(state)
        return state
