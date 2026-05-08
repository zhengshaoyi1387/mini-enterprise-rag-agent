from __future__ import annotations

from typing import Any

from mini_rag.config import Settings
from mini_rag.graph.nodes import AgenticRAGNodes, create_initial_state
from mini_rag.graph.state import AgentState


class AgenticRAGWorkflow:
    """LangGraph workflow for the simplified enterprise Agent.

    Main graph:
        load_context -> check_permission -> understand_query -> route
        route=rag    -> plan_retrieval -> retrieve -> reflect -> generate_answer
        route=tool   -> call_tool -> generate_answer
        route=direct -> generate_answer
        route=reject -> generate_answer
        generate_answer -> update_memory -> END
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
        workflow.add_node("load_context", self.nodes.load_context)
        workflow.add_node("check_permission", self.nodes.check_permission)
        workflow.add_node("understand_query", self.nodes.understand_query)
        workflow.add_node("route", self.nodes.route)
        workflow.add_node("plan_retrieval", self.nodes.plan_retrieval)
        workflow.add_node("retrieve", self.nodes.retrieve)
        workflow.add_node("reflect_evidence", self.nodes.reflect_evidence)
        workflow.add_node("call_tool", self.nodes.call_tool)
        workflow.add_node("generate_answer", self.nodes.generate_answer)
        workflow.add_node("update_memory", self.nodes.update_memory)

        workflow.set_entry_point("load_context")
        workflow.add_edge("load_context", "check_permission")
        workflow.add_edge("check_permission", "understand_query")
        workflow.add_edge("understand_query", "route")
        workflow.add_conditional_edges(
            "route",
            self.nodes.next_after_route,
            {
                "plan_retrieval": "plan_retrieval",
                "call_tool": "call_tool",
                "generate_answer": "generate_answer",
            },
        )
        workflow.add_edge("call_tool", "generate_answer")
        workflow.add_edge("plan_retrieval", "retrieve")
        workflow.add_conditional_edges(
            "retrieve",
            self.nodes.after_retrieve,
            {
                "reflect_evidence": "reflect_evidence",
                "generate_answer": "generate_answer",
            },
        )
        workflow.add_conditional_edges(
            "reflect_evidence",
            self.nodes.after_reflect,
            {
                "retrieve": "retrieve",
                "generate_answer": "generate_answer",
            },
        )
        workflow.add_edge("generate_answer", "update_memory")
        workflow.add_edge("update_memory", END)
        return workflow.compile()

    def _run_fallback(self, state: AgentState) -> AgentState:
        state = self._run_until_generate(state)
        state = self.nodes.generate_answer(state)
        state = self.nodes.update_memory(state)
        return state

    def _run_until_generate(self, state: AgentState) -> AgentState:
        state = self.nodes.load_context(state)
        state = self.nodes.check_permission(state)
        state = self.nodes.understand_query(state)
        state = self.nodes.route(state)
        next_node = self.nodes.next_after_route(state)
        if next_node == "call_tool":
            state = self.nodes.call_tool(state)
        elif next_node == "plan_retrieval":
            state = self.nodes.plan_retrieval(state)
            state = self.nodes.retrieve(state)
            if self.nodes.after_retrieve(state) == "reflect_evidence":
                state = self.nodes.reflect_evidence(state)
            while self.nodes.after_reflect(state) == "retrieve":
                state = self.nodes.retrieve(state)
                if self.nodes.after_retrieve(state) == "reflect_evidence":
                    state = self.nodes.reflect_evidence(state)
                else:
                    break
        return state
