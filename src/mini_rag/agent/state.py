from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """LangGraph 工作流的共享状态。

    新手理解：
    State 就是“每个节点都能读写的运行时白板”。
    节点不直接互相调用，而是通过 State 传递信息：
    - manage_context 写入 standalone_query。
    - llm_router 写入 route。
    - execute_tool 写入 retrieved_docs / observations。
    - final 写入 final_answer。
    """

    # 用户输入和请求级标识。
    question: str
    user_query: str
    session_id: str | None
    user_id: str
    role: str
    workflow_run_id: str
    trace_id: str
    retrieval_mode: str | None
    enable_rerank: bool | None

    # LLM 上下文管理节点产物。
    conversation_summary: str
    selected_history: list[dict[str, Any]]
    standalone_query: str
    resolved_entities: list[str]
    resolved_topic: str
    context_events: list[dict[str, Any]]

    # LLM Router 节点产物。
    route: str
    router_decision: dict[str, Any]
    router_reason: str
    risk_level: str

    # 工具执行节点产物。RAG 也被视为 search_knowledge_base 工具调用。
    retrieved_docs: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    retrieval_plan: dict[str, Any]
    retrieval_queries: list[str]
    pending_search_queries: list[str]
    evidence_assessment: dict[str, Any]
    reflect_round: int

    # 控制与可观测字段。
    step_count: int
    max_steps: int
    final_answer: str
    error: str | None
    node_trace: list[dict[str, Any]]
