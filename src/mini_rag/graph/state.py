from __future__ import annotations

from typing import Any, Literal, TypedDict

RouteName = Literal["direct", "rag", "tool", "reject"]


class AgentState(TypedDict, total=False):
    """LangGraph 单次运行状态。

    这个 State 只在本轮 workflow_run_id 内有效，不作为长期会话记忆。
    session_id 只用于读取/写入 memory store。
    """

    # request
    question: str
    session_id: str | None
    workflow_run_id: str
    retrieval_mode: str | None
    enable_rerank: bool | None
    requested_kbs: list[str]
    allowed_kbs: list[str]
    used_kbs: list[str]

    # memory
    conversation_summary: str
    history: list[dict[str, Any]]

    # understanding / routing
    intent: str
    route: RouteName
    risk_level: str
    standalone_query: str
    topic: str
    entities: list[str]
    query_reason: str
    router_reason: str
    required_tools: list[str]
    selected_tool: str | None
    tool_input: dict[str, Any]

    # retrieval
    search_tasks: list[dict[str, Any]]
    pending_search_tasks: list[dict[str, Any]]
    executed_queries: list[str]
    _executed_query_keys: list[str]
    _retrieval_cache: dict[str, Any]
    retrieved_docs: list[Any]
    sources: list[dict[str, Any]]
    evidence_brief: str
    observations: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]

    # reflection / generation
    evidence_assessment: dict[str, Any]
    skipped_reflection_reason: str | None
    reflect_round: int
    final_answer: str
    memory_update: dict[str, Any]

    # trace / errors
    node_trace: list[dict[str, Any]]
    llm_calls: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]
    error: str | None
