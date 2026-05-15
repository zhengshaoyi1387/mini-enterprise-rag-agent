from __future__ import annotations

from typing import Any, Literal, TypedDict

RouteName = Literal["direct", "rag", "tool", "reject"]


class AgentState(TypedDict, total=False):
    """LangGraph 单次运行状态。"""

    # request
    question: str
    user_query: str
    session_id: str | None
    user_id: str
    role: str
    workflow_run_id: str
    trace_id: str
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
    message_type: str
    context_usage: str
    available_tool_contracts: str
    planning_context: dict[str, Any]
    raw_plan: dict[str, Any]
    plan_validation: dict[str, Any]
    execution_plan: dict[str, Any]
    task_queue: list[dict[str, Any]]
    current_task: dict[str, Any]
    task_results: list[dict[str, Any]]
    completed_tasks: list[str]
    time_requirement: dict[str, Any]
    knowledge_requirement: dict[str, Any]
    prepared_tool_input: dict[str, Any]
    route: RouteName
    risk_level: str
    standalone_query: str
    topic: str
    entities: list[str]
    query_reason: str
    router_reason: str
    required_tools: list[str]
    candidate_tool: str | None
    selected_tool: str | None
    selected_action: str | None
    tool_input: dict[str, Any]
    tool_result: dict[str, Any]
    previous_tool_context: dict[str, Any]
    current_tool_context: dict[str, Any]
    time_reference: dict[str, Any]
    needs_time_resolution: bool
    relative_time: str | None
    missing_required_slots: list[str]

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
    completion_assessment: dict[str, Any]
    completion_reflect_round: int
    skipped_reflection_reason: str | None
    reflect_round: int
    final_answer: str
    memory_update: dict[str, Any]

    # trace / errors
    node_trace: list[dict[str, Any]]
    llm_calls: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]
    error: str | None
