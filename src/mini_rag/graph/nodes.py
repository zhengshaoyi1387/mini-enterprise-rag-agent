from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import uuid4

from mini_rag.agent.context_store import SQLiteContextStore
from mini_rag.config import Settings
from mini_rag.graph.prompts import (
    COMPLETION_REFLECT_SYSTEM,
    GENERATE_ANSWER_SYSTEM,
    MEMORY_UPDATE_SYSTEM,
    PLAN_RETRIEVAL_SYSTEM,
    REFLECT_EVIDENCE_SYSTEM,
    ROUTE_SYSTEM,
    UNDERSTAND_QUERY_SYSTEM,
    format_answer_user,
    format_completion_reflect_user,
    format_memory_user,
    format_plan_user,
    format_reflect_user,
    format_route_user,
    format_understand_user,
)
from mini_rag.graph.state import AgentState
from mini_rag.graph.utils import (
    NodeTimer,
    coerce_list,
    compact_evidence_text,
    dedupe_keep_order,
    document_key,
    document_to_source,
    format_evidence_text,
    get_message_content,
    safe_json_loads,
    strip_citations_and_metadata,
    truncate,
)
from mini_rag.utils import stable_hash
from mini_rag.security.auth_store import SQLiteAuthStore
from mini_rag.security.permissions import (
    assert_can_access_kbs,
    assert_tool_action_permission,
    assert_tool_permission,
    normalize_role,
)
from mini_rag.tools.daily_tools import build_default_tool_registry
from mini_rag.tools.datetime_tool import get_current_datetime
from mini_rag.tools.contracts import validate_tool_input
from pydantic import ValidationError


CANONICAL_RELATIVE_RANGES: set[str] = {
    "today",
    "yesterday",
    "tomorrow",
    "this_week",
    "last_week",
    "next_week",
    "week_after_next",
    "next_next_week",
    "this_month",
    "last_month",
    "next_month",
    "month_after_next",
    "next_next_month",
}

RELATIVE_RANGE_ALIASES: dict[str, str] = {
    "next_next_week": "week_after_next",
    "next_next_month": "month_after_next",
}


class AgenticRAGNodes:
    """Agentic RAG 的 LangGraph 节点集合。

    LLM 负责语义理解、检索规划、证据反思和最终表达；
    代码负责状态隔离、结构化解析、检索执行、去重、trace 和记忆清洗。
    """

    def __init__(self, settings: Settings, llm: Any | None = None, retriever: Any | None = None):
        self.settings = settings
        self.context_store = SQLiteContextStore(settings.context_db_path)
        if llm is None:
            from mini_rag.models.qwen import build_qwen_chat_model, build_qwen_control_model

            self.answer_llm = build_qwen_chat_model(settings)
            self.control_llm = build_qwen_control_model(settings)
        else:
            # 测试或自定义运行时可注入一个假 LLM；默认同时承担控制节点和最终回答。
            self.answer_llm = llm
            self.control_llm = llm
        self.llm = self.answer_llm
        self.retriever: Any | None = retriever
        self.tool_registry = build_default_tool_registry()
        self.auth_store = SQLiteAuthStore(settings.auth_db_path)
        self._role_policy_snapshots: dict[str, Any] = {}

    # ---------- public LangGraph nodes ----------
    def load_context(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "load_context"):
            session_id = state.get("session_id")
            context = self.context_store.get_context(session_id, max_turns=self.settings.session_max_turns)
            state["conversation_summary"] = context.summary
            state["history"] = [self._turn_to_history_item(turn) for turn in context.turns]
            state["previous_tool_context"] = self._extract_previous_tool_context(context.turns)
            state.setdefault("observations", [])
            state.setdefault("node_trace", [])
            state.setdefault("tool_calls", [])
            state.setdefault("retrieved_docs", [])
            state.setdefault("sources", [])
            state.setdefault("evidence_brief", "")
            state.setdefault("executed_queries", [])
            state.setdefault("_executed_query_keys", [])
            state.setdefault("_retrieval_cache", {})
            state.setdefault("llm_calls", [])
            state.setdefault("reflect_round", 0)
        return state

    def check_permission(self, state: AgentState) -> AgentState:
        """Compute allowed knowledge bases before any retrieval node runs.

        Permission rules live at the KB level. This node never retrieves
        documents; it only converts role + requested_kbs into allowed_kbs.
        Later retriever calls receive allowed_kbs so unauthorized chunks are not
        fetched into context.
        """

        with NodeTimer(state, "check_permission"):
            role = normalize_role(state.get("role"))
            requested_kbs = state.get("requested_kbs") or []
            role_policies = self._get_role_policies(state)
            try:
                allowed_kbs = assert_can_access_kbs(role, requested_kbs, role_policies=role_policies)
                state["allowed_kbs"] = allowed_kbs
                state["used_kbs"] = allowed_kbs
                state.setdefault("audit_events", []).append(
                    {
                        "event": "kb_permission_check",
                        "role": role,
                        "requested_kbs": requested_kbs,
                        "allowed_kbs": allowed_kbs,
                        "decision": "allowed",
                    }
                )
                state.setdefault("observations", []).append(
                    {"type": "kb_permission_check", "role": role, "requested_kbs": requested_kbs, "allowed_kbs": allowed_kbs}
                )
            except PermissionError as exc:
                state["route"] = "reject"
                state["risk_level"] = "medium"
                state["error"] = str(exc)
                state["final_answer"] = "你没有权限访问所请求的知识库。"
                state.setdefault("allowed_kbs", [])
                state.setdefault("used_kbs", [])
                state.setdefault("audit_events", []).append(
                    {
                        "event": "kb_permission_check",
                        "role": role,
                        "requested_kbs": requested_kbs,
                        "decision": "blocked",
                        "reason": str(exc),
                    }
                )
        return state

    def build_capability_catalog(self, state: AgentState) -> AgentState:
        """Build the permission-aware capability catalog for the planner.

        This node does not call an LLM. It exposes only the tools/actions the
        current role may plan against. The executor still re-checks permission.
        """
        with NodeTimer(state, "build_capability_catalog"):
            if state.get("error") and state.get("route") == "reject":
                return state
            role = normalize_role(state.get("role"))
            role_policies = self._get_role_policies(state)
            contracts = self.tool_registry.format_tool_contracts_for_prompt(role=role, role_policies=role_policies)
            state["candidate_tool"] = None
            state["available_tool_contracts"] = contracts
            state.setdefault("observations", []).append(
                {
                    "type": "capability_catalog",
                    "role": role,
                    "contract_chars": len(str(contracts)),
                }
            )
        return state

    def build_planning_context(self, state: AgentState) -> AgentState:
        """Build compact non-LLM context for planning.

        This keeps multi-turn semantics without sending raw conversation_summary
        or long history to the Planner. It is state compression, not routing.
        """
        with NodeTimer(state, "build_planning_context"):
            history = state.get("history") or []
            last_turn = history[-1] if history else {}
            previous_tool_context = state.get("previous_tool_context") or {}
            tool_input = previous_tool_context.get("tool_input") if isinstance(previous_tool_context.get("tool_input"), dict) else {}
            compact_tool_input = {
                str(k): v
                for k, v in tool_input.items()
                if str(k) not in {"query", "user_id", "role", "file_path"} and not str(k).startswith("_")
            }
            planning_context = {
                "last_turn": {
                    "user": str(last_turn.get("question") or "")[:160],
                    "standalone_query": str(last_turn.get("standalone_query") or "")[:160],
                    "assistant_brief": truncate(strip_citations_and_metadata(str(last_turn.get("memory_answer") or last_turn.get("answer") or "")), 220),
                    "intent": last_turn.get("intent") or "",
                    "topic": last_turn.get("topic") or "",
                } if last_turn else {},
                "previous_tool_context": {
                    "domain": previous_tool_context.get("domain"),
                    "tool_name": previous_tool_context.get("tool_name"),
                    "tool_input": compact_tool_input,
                    "result_summary": truncate(str(previous_tool_context.get("result_summary") or ""), 260),
                } if previous_tool_context else {},
            }
            # Drop empty values to reduce prompt size.
            planning_context = {k: v for k, v in planning_context.items() if v}
            state["planning_context"] = planning_context
            state.setdefault("observations", []).append({"type": "planning_context", "keys": sorted(planning_context.keys())})
        return state

    def plan_intent(self, state: AgentState) -> AgentState:
        """LLM planning node.

        The planner owns message classification, context usage, route choice,
        tool/action choice, time_requirement and knowledge_requirement. It does
        not execute tools and does not receive keyword candidates.
        """
        with NodeTimer(state, "plan_intent"):
            if state.get("error") and state.get("route") == "reject":
                return state
            question = state.get("question", "")
            role = normalize_role(state.get("role"))
            contracts = state.get("available_tool_contracts")
            if not contracts:
                role_policies = self._get_role_policies(state)
                contracts = self.tool_registry.format_tool_contracts_for_prompt(role=role, role_policies=role_policies)
                state["available_tool_contracts"] = contracts

            from mini_rag.graph.prompts import format_plan_intent_user
            user_prompt = format_plan_intent_user(
                question=question,
                available_tool_contracts=str(contracts),
                role=role,
                planning_context=state.get("planning_context", {}),
            )
            payload = self._invoke_json(
                state=state,
                node="plan_intent",
                system=UNDERSTAND_QUERY_SYSTEM,
                user=user_prompt,
                default={
                    "message_type": "business_question",
                    "context_usage": "none",
                    "intent": "rag_fact",
                    "route": "rag",
                    "standalone_query": question,
                    "topic": "",
                    "entities": [],
                    "risk_level": "low",
                    "selected_tool": None,
                    "selected_action": None,
                    "required_tools": [],
                    "tool_input": {},
                    "time_requirement": {
                        "has_time_requirement": False,
                        "time_reference_type": "none",
                        "canonical_relative": None,
                        "absolute_date": None,
                        "date_range": None,
                        "requires_current_datetime": False,
                    },
                    "knowledge_requirement": {
                        "requires_company_knowledge": False,
                        "known_from_user_message": False,
                        "should_use_rag": True,
                    },
                    "missing_required_slots": [],
                    "reason": "planner fallback",
                },
            )
            if not isinstance(payload, dict):
                payload = {}
            state["raw_plan"] = payload
            self._apply_plan_payload_to_state(state, payload, normalize=False)
            state.setdefault("observations", []).append(
                {
                    "type": "plan_intent",
                    "message_type": state.get("message_type"),
                    "context_usage": state.get("context_usage"),
                    "intent": state.get("intent"),
                    "route": state.get("route"),
                    "standalone_query": state.get("standalone_query"),
                    "selected_tool": state.get("selected_tool"),
                    "selected_action": state.get("selected_action"),
                    "tool_input": state.get("tool_input", {}),
                    "time_requirement": state.get("time_requirement", {}),
                    "knowledge_requirement": state.get("knowledge_requirement", {}),
                    "reason": state.get("query_reason", ""),
                }
            )
        return state

    def validate_plan(self, state: AgentState) -> AgentState:
        """Validate planner output against contracts and security boundaries.

        This node does structural normalization only. It must not infer business
        semantics from the Chinese text.
        """
        with NodeTimer(state, "validate_plan"):
            if state.get("error") and state.get("route") == "reject":
                return state
            role = normalize_role(state.get("role"))
            role_policies = self._get_role_policies(state)
            raw_plan = dict(state.get("raw_plan") or {})
            if not raw_plan:
                raw_plan = self._state_to_plan_payload(state)
            normalized = self._normalize_planner_contract(raw_plan, role=role, role_policies=role_policies, state=state)
            if self._is_dangerous_question(state.get("question", ""), str(normalized.get("standalone_query") or "")):
                normalized["route"] = "reject"
                normalized["intent"] = "reject"
                normalized["message_type"] = "unsafe"
                normalized["risk_level"] = "high"
            self._apply_plan_payload_to_state(state, normalized, normalize=True)
            state["plan_validation"] = {
                "route": state.get("route"),
                "intent": state.get("intent"),
                "selected_tool": state.get("selected_tool"),
                "selected_action": state.get("selected_action"),
                "normalization_reason": normalized.get("normalization_reason"),
            }
            state.setdefault("observations", []).append(
                {
                    "type": "plan_validation",
                    **state["plan_validation"],
                }
            )
        return state

    def understand_query(self, state: AgentState) -> AgentState:
        """Backward-compatible wrapper for older callers/tests.

        The main workflow now uses build_capability_catalog -> plan_intent ->
        validate_plan. Keeping this wrapper avoids breaking external imports.
        """
        state = self.build_capability_catalog(state)
        state = self.build_planning_context(state)
        state = self.plan_intent(state)
        state = self.validate_plan(state)
        return state

    def route(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "route"):
            if state.get("error") and state.get("route") == "reject":
                return state
            # route 已由 plan_intent 的 LLM 调用产出；这里仅做安全校验和 trace 分隔。
            route = str(state.get("route") or "rag")
            if route not in {"direct", "rag", "tool", "reject"}:
                route = "rag"
            if self._is_dangerous_question(state.get("question", ""), state.get("standalone_query", "")):
                route = "reject"
                state["risk_level"] = "high"
            state["route"] = route  # type: ignore[assignment]
            state.setdefault("risk_level", "low")
            state.setdefault("required_tools", [])
            state.setdefault("router_reason", state.get("query_reason", ""))
            state.setdefault("observations", []).append(
                {"type": "route", "route": route, "risk_level": state["risk_level"], "reason": state["router_reason"]}
            )
        return state

    def call_tool(self, state: AgentState) -> AgentState:
        """Execute a registered tool through schema validation and action permissions."""

        with NodeTimer(state, "call_tool"):
            role = normalize_role(state.get("role"))
            tool_name = str(state.get("selected_tool") or (state.get("required_tools") or [None])[0] or "")
            before_tool_calls = len(state.get("tool_calls") or [])
            if not tool_name:
                state["route"] = "reject"
                state["error"] = "No tool selected"
                state["final_answer"] = "没有识别到可执行的企业能力。"
                state["tool_result"] = {"error": "no tool selected"}
                self._record_tool_task_result(state, before_tool_calls)
                return state
            if not self.tool_registry.has_tool(tool_name):
                state["error"] = f"Unknown tool: {tool_name}"
                state["final_answer"] = "没有识别到可执行的企业能力。"
                state["tool_result"] = {"error": "unknown tool", "tool_name": tool_name}
                state.setdefault("tool_calls", []).append({"tool_name": tool_name, "ok": False, "reason": "unknown tool"})
                state.setdefault("audit_events", []).append(
                    {"event": "tool_call", "tool_name": tool_name, "role": role, "decision": "blocked", "reason": "unknown tool"}
                )
                self._record_tool_task_result(state, before_tool_calls)
                return state
            try:
                payload = self._build_tool_payload(state, tool_name, role)
                action = str(state.get("selected_action") or payload.get("action") or "*").strip().lower() or "*"
                assert_tool_action_permission(role, tool_name, action, role_policies=self._get_role_policies(state))
                result = self.tool_registry.invoke(tool_name, payload)
                if isinstance(result, dict):
                    result = dict(result)
                    result.setdefault("tool_name", tool_name)
                state["tool_input"] = payload
                state["tool_result"] = result
                if result.get("error"):
                    state["final_answer"] = self._friendly_tool_error(tool_name, result, role=role, action=action)
                else:
                    current_context = self._build_current_tool_context(tool_name, payload, result)
                    current_context["trace_id"] = state.get("trace_id")
                    state["current_tool_context"] = current_context
                    state["final_answer"] = ""
                state.setdefault("tool_calls", []).append(
                    {
                        "tool_name": tool_name,
                        "action": action,
                        "args": payload,
                        "ok": not bool(result.get("error")),
                        "risk_level": result.get("risk_level", "low"),
                        "error": result.get("error"),
                    }
                )
                state.setdefault("observations", []).append({"type": "tool", "tool_name": tool_name, "result": result})
                state.setdefault("audit_events", []).append(
                    {
                        "event": "tool_call",
                        "tool_name": tool_name,
                        "role": role,
                        "decision": "blocked" if result.get("error") == "permission denied" else "allowed",
                        "action": action,
                        "reason": result.get("error"),
                    }
                )
            except PermissionError as exc:
                action = str(state.get("selected_action") or (state.get("tool_input") or {}).get("action") or "*")
                state["route"] = "direct"
                state["intent"] = "permission_required"
                state["error"] = str(exc)
                state["final_answer"] = self._friendly_permission_answer(role, tool_name, action)
                state.setdefault("tool_calls", []).append({"tool_name": tool_name, "action": action, "ok": False, "reason": "permission denied"})
                state.setdefault("audit_events", []).append(
                    {"event": "tool_call", "tool_name": tool_name, "action": action, "role": role, "decision": "blocked", "reason": str(exc)}
                )
            except ValidationError as exc:
                state["final_answer"] = self._friendly_tool_validation_error(tool_name, exc)
                state["tool_result"] = {
                    "error": "tool_input_validation_failed",
                    "message": str(exc),
                    "tool_name": tool_name,
                }
                state.setdefault("tool_calls", []).append(
                    {"tool_name": tool_name, "ok": False, "reason": "tool_input_validation_failed", "validation_error": str(exc)}
                )
                state.setdefault("audit_events", []).append(
                    {"event": "tool_call", "tool_name": tool_name, "role": role, "decision": "blocked", "reason": "tool_input_validation_failed"}
                )
            self._record_tool_task_result(state, before_tool_calls)
        return state

    def completion_reflect(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "completion_reflect"):
            if state.get("route") in {"reject", "direct"} and not state.get("task_results"):
                state["completion_assessment"] = {
                    "ready_to_answer": True,
                    "completed_objectives": [],
                    "missing_objectives": [],
                    "unsupported_parts": [],
                    "next_action": "answer",
                    "reason": "direct route",
                }
                return state
            next_planned_task = self._prime_next_task(state)
            if next_planned_task:
                state["completion_assessment"] = {
                    "ready_to_answer": False,
                    "completed_objectives": [str(x) for x in state.get("completed_tasks", [])],
                    "missing_objectives": [str(next_planned_task.get("objective") or next_planned_task.get("task_id") or "")],
                    "unsupported_parts": [],
                    "next_action": "continue",
                    "followup_tasks": [next_planned_task],
                    "reason": "planned task remains",
                }
                state.setdefault("observations", []).append({"type": "completion_reflection", **state["completion_assessment"]})
                return state
            completion_round = int(state.get("completion_reflect_round") or 0) + 1
            state["completion_reflect_round"] = completion_round
            evidence_text = state.get("evidence_brief") or compact_evidence_text(state.get("retrieved_docs", []), entities=state.get("entities", []))
            payload = self._invoke_json(
                state=state,
                node="completion_reflect",
                system=COMPLETION_REFLECT_SYSTEM,
                user=format_completion_reflect_user(
                    question=state.get("question", ""),
                    execution_plan=state.get("execution_plan", {}),
                    task_results=state.get("task_results", []),
                    evidence_text=evidence_text,
                    sources=state.get("sources", []),
                    completion_round=completion_round,
                ),
                default={
                    "ready_to_answer": True,
                    "completed_objectives": [],
                    "missing_objectives": [],
                    "unsupported_parts": [],
                    "next_action": "answer",
                    "followup_tasks": [],
                    "reason": "completion reflection fallback",
                },
            )
            followups = [
                self._normalize_execution_task(task, idx, state.get("raw_plan", {}))
                for idx, task in enumerate(coerce_list(payload.get("followup_tasks")))
                if isinstance(task, dict)
            ]
            completed = set(state.get("completed_tasks") or [])
            followups = [task for task in followups if task.get("task_id") not in completed and task.get("kind")]
            max_replans = max(0, int(getattr(self.settings, "agent_completion_max_replans", 2) or 0))
            ready = bool(payload.get("ready_to_answer"))
            next_action = str(payload.get("next_action") or "answer").lower()
            if completion_round > max_replans:
                ready = True
                next_action = "answer"
                followups = []
            elif not ready and next_action in {"continue", "replan"} and followups:
                state["task_queue"] = list(state.get("task_queue") or []) + followups
                self._prime_next_task(state)
            else:
                followups = []
                if not ready:
                    next_action = "answer"
                    ready = True
            state["completion_assessment"] = {
                "ready_to_answer": ready,
                "completed_objectives": [str(x) for x in coerce_list(payload.get("completed_objectives"))],
                "missing_objectives": [str(x) for x in coerce_list(payload.get("missing_objectives"))],
                "unsupported_parts": [str(x) for x in coerce_list(payload.get("unsupported_parts"))],
                "next_action": next_action,
                "followup_tasks": followups,
                "reason": str(payload.get("reason") or ""),
            }
            state.setdefault("observations", []).append({"type": "completion_reflection", **state["completion_assessment"]})
        return state

    def plan_retrieval(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "plan_retrieval"):
            user_prompt = format_plan_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                intent=state.get("intent", ""),
                topic=state.get("topic", ""),
                entities=state.get("entities", []),
            )
            payload = self._invoke_json(
                state=state,
                node="plan_retrieval",
                system=PLAN_RETRIEVAL_SYSTEM,
                user=user_prompt,
                default={
                    "search_tasks": [
                        {
                            "query": state.get("standalone_query") or state.get("question", ""),
                            "purpose": "answer_question",
                            "target_entity": None,
                        }
                    ],
                    "reason": "检索规划解析失败，使用独立问题兜底。",
                },
            )
            raw_tasks = payload.get("search_tasks")
            if raw_tasks is None:
                raw_tasks = payload.get("search_queries")
            tasks = self._normalize_tasks(raw_tasks, fallback_query=state.get("standalone_query") or state.get("question", ""))
            tasks = self._optimize_search_tasks(state, tasks)
            state["search_tasks"] = tasks
            state["pending_search_tasks"] = tasks
            state.setdefault("observations", []).append({"type": "retrieval_plan", "search_tasks": tasks, "reason": payload.get("reason", "")})
        return state

    def retrieve(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "retrieve"):
            # RAG retrieval is treated as a tool-like action. The model may
            # route to retrieval, but program-side permission is checked here
            # immediately before executing the underlying retriever.
            role = normalize_role(state.get("role"))
            assert_tool_permission(role, "search_knowledge_base", role_policies=self._get_role_policies(state))
            state.setdefault("observations", []).append(
                {
                    "type": "permission_check",
                    "scope": "tool",
                    "tool_name": "search_knowledge_base",
                    "role": role,
                    "allowed": True,
                }
            )
            retriever = self._get_retriever()
            pending = state.get("pending_search_tasks") or []
            if not pending:
                state.setdefault("observations", []).append({"type": "retrieve", "message": "没有待检索任务，跳过。"})
                self._record_rag_task_result(state)
                return state

            all_docs = list(state.get("retrieved_docs") or [])
            previous_doc_count = len(dedupe_keep_order(all_docs, key=document_key))
            executed_queries = list(state.get("executed_queries") or [])
            executed_query_keys = list(state.get("_executed_query_keys") or [])
            sources = list(state.get("sources") or [])
            tool_calls = state.setdefault("tool_calls", [])
            observations = state.setdefault("observations", [])
            executed_set = set(executed_query_keys)
            retrieval_cache = state.setdefault("_retrieval_cache", {})
            cache_enabled = bool(getattr(self.settings, "agent_enable_retrieval_cache", True))

            runnable_tasks: list[dict[str, Any]] = []
            for task in pending:
                query = str(task.get("query") or "").strip()
                query_key = self._normalize_query_key(query)
                if not query:
                    continue
                if cache_enabled and query_key in retrieval_cache:
                    cached = retrieval_cache[query_key]
                    docs = list(cached.get("docs") or [])
                    retrieval_trace = dict(cached.get("trace") or {})
                    retrieval_trace["retrieval_cache_hit"] = True
                    if retrieval_trace.get("rerank_enabled"):
                        retrieval_trace["rerank_cache_hit"] = True
                    retrieval_trace["query"] = query
                    executed_queries.append(query)
                    executed_query_keys.append(query_key)
                    tool_calls.append({"tool_name": "search_knowledge_base", "args": {"query": query, "kb_ids": state.get("used_kbs", [])}, "ok": True, "cache_hit": True})
                    observations.append(
                        {
                            "type": "tool",
                            "tool_name": "search_knowledge_base",
                            "query": query,
                            "task": task,
                            "retrieval_trace": retrieval_trace,
                        }
                    )
                    all_docs.extend(docs)
                    continue
                if query_key in executed_set:
                    continue
                runnable_tasks.append(task)
                executed_set.add(query_key)

            def run_task(task: dict[str, Any]) -> tuple[dict[str, Any], list[Any], dict[str, Any]]:
                query = str(task.get("query") or "").strip()
                top_k = int(task.get("top_k") or self.settings.top_k)
                candidate_k = int(task.get("candidate_k") or self.settings.candidate_k)
                enable_rerank = task.get("enable_rerank", state.get("enable_rerank"))
                try:
                    docs, retrieval_trace = retriever.search(
                        query,
                        top_k=top_k,
                        candidate_k=candidate_k,
                        retrieval_mode=state.get("retrieval_mode"),
                        enable_rerank=enable_rerank,
                        kb_ids=state.get("used_kbs", []),
                    )
                except TypeError as exc:
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    try:
                        docs, retrieval_trace = retriever.search(
                            query,
                            retrieval_mode=state.get("retrieval_mode"),
                            enable_rerank=enable_rerank,
                            kb_ids=state.get("used_kbs", []),
                        )
                    except TypeError as second_exc:
                        if "unexpected keyword argument" not in str(second_exc):
                            raise
                        docs, retrieval_trace = retriever.search(
                            query,
                            retrieval_mode=state.get("retrieval_mode"),
                            enable_rerank=enable_rerank,
                        )
                retrieval_trace.setdefault("retrieval_cache_hit", False)
                retrieval_trace.setdefault("rerank_cache_hit", False)
                return task, docs, retrieval_trace

            def record_result(task: dict[str, Any], docs: list[Any], retrieval_trace: dict[str, Any]) -> None:
                query = str(task.get("query") or "").strip()
                query_key = self._normalize_query_key(query)
                executed_queries.append(query)
                executed_query_keys.append(query_key)
                if cache_enabled:
                    retrieval_cache[query_key] = {"docs": list(docs), "trace": dict(retrieval_trace)}
                tool_calls.append({"tool_name": "search_knowledge_base", "args": {"query": query, "kb_ids": state.get("used_kbs", [])}, "ok": True})
                observations.append(
                    {
                        "type": "tool",
                        "tool_name": "search_knowledge_base",
                        "query": query,
                        "task": task,
                        "retrieval_trace": retrieval_trace,
                    }
                )
                all_docs.extend(docs)

            max_workers = max(1, int(getattr(self.settings, "agent_retrieval_workers", 1) or 1))
            if len(runnable_tasks) > 1 and max_workers > 1:
                with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable_tasks))) as pool:
                    futures = [pool.submit(run_task, task) for task in runnable_tasks]
                    for future in as_completed(futures):
                        task, docs, retrieval_trace = future.result()
                        record_result(task, docs, retrieval_trace)
            else:
                for task in runnable_tasks:
                    task, docs, retrieval_trace = run_task(task)
                    record_result(task, docs, retrieval_trace)

            all_docs = dedupe_keep_order(all_docs, key=document_key)
            state["retrieval_made_progress"] = len(all_docs) > previous_doc_count
            sources = [document_to_source(doc) for doc in all_docs]
            state["retrieved_docs"] = all_docs
            state["sources"] = sources
            state["executed_queries"] = executed_queries
            state["_executed_query_keys"] = executed_query_keys
            state["_retrieval_cache"] = retrieval_cache
            state["pending_search_tasks"] = []
            state["evidence_brief"] = compact_evidence_text(
                all_docs,
                entities=state.get("entities", []),
                max_total_chars=int(getattr(self.settings, "agent_evidence_char_limit", 4200) or 4200),
            )
            self._record_rag_task_result(state)
        return state

    def reflect_evidence(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "reflect_evidence"):
            reflect_round = int(state.get("reflect_round") or 0) + 1
            state["reflect_round"] = reflect_round
            evidence_text = state.get("evidence_brief") or compact_evidence_text(state.get("retrieved_docs", []), entities=state.get("entities", []))
            user_prompt = format_reflect_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                executed_queries=state.get("executed_queries", []),
                evidence_text=evidence_text,
            )
            payload = self._invoke_json(
                state=state,
                node="reflect_evidence",
                system=REFLECT_EVIDENCE_SYSTEM,
                user=user_prompt,
                default={
                    "is_sufficient": bool(state.get("retrieved_docs")),
                    "can_answer_partial": bool(state.get("retrieved_docs")),
                    "should_continue_retrieval": False,
                    "missing_information": [],
                    "followup_tasks": [],
                    "stop_reason": "证据反思解析失败，基于现有证据进入回答。",
                    "reason": "证据反思解析失败，基于现有证据进入回答。",
                },
            )
            followup_tasks = self._normalize_tasks(payload.get("followup_tasks"), fallback_query="")
            if not followup_tasks and payload.get("followup_queries") is not None:
                followup_tasks = self._normalize_tasks(payload.get("followup_queries"), fallback_query="")
            executed = set(state.get("executed_queries", []))
            executed_keys = set(state.get("_executed_query_keys", []))
            followup_tasks = [
                task for task in followup_tasks
                if str(task.get("query", "")).strip() not in executed
                and self._normalize_query_key(str(task.get("query", ""))) not in executed_keys
            ]
            max_followups = max(0, int(getattr(self.settings, "agent_max_followup_tasks", 2) or 0))
            followup_tasks = followup_tasks[:max_followups]
            can_answer_partial = bool(payload.get("can_answer_partial"))
            is_sufficient = bool(payload.get("is_sufficient"))
            should_continue = bool(payload.get("should_continue_retrieval"))
            if "should_continue_retrieval" not in payload:
                should_continue = bool(followup_tasks) and not is_sufficient
            stop_reason = str(payload.get("stop_reason") or "")
            if is_sufficient or not should_continue:
                followup_tasks = []
                stop_reason = stop_reason or ("evidence_sufficient" if is_sufficient else "llm_decided_no_more_retrieval")
            # 循环边界由代码控制；LLM 只能建议 followup_tasks。
            if reflect_round >= max(1, int(getattr(self.settings, "agent_reflect_max_rounds", 1) or 1)):
                followup_tasks = []
                stop_reason = stop_reason or "max_reflection_rounds_reached"
            state["evidence_assessment"] = {
                "is_sufficient": is_sufficient,
                "can_answer_partial": can_answer_partial,
                "should_continue_retrieval": should_continue,
                "missing_information": [str(x) for x in coerce_list(payload.get("missing_information"))],
                "followup_tasks": followup_tasks,
                "reason": str(payload.get("reason") or ""),
            }
            if stop_reason:
                state["evidence_assessment"]["stop_reason"] = stop_reason
            state["pending_search_tasks"] = followup_tasks
            state.setdefault("observations", []).append({"type": "evidence_reflection", **state["evidence_assessment"]})
        return state

    def generate_answer(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "generate_answer"):
            if state.get("route") == "reject":
                state["final_answer"] = state.get("final_answer") or "抱歉，这个请求存在安全风险，我不能执行。"
                return state
            if state.get("route") == "direct" and state.get("intent") == "smalltalk":
                state["final_answer"] = state.get("final_answer") or "你好，我是企业知识库助手。你可以问我公司制度、考勤、公司日程等问题。"
                return state
            if state.get("route") == "direct" and state.get("intent") == "permission_required":
                state["final_answer"] = state.get("final_answer") or self._permission_required_direct_answer(state)
                return state
            evidence_text = state.get("evidence_brief") or compact_evidence_text(state.get("retrieved_docs", []), entities=state.get("entities", []))
            user_prompt = format_answer_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                route=state.get("route", "direct"),
                model_name=self.settings.qwen_chat_model,
                evidence_assessment=state.get("evidence_assessment", {}),
                evidence_text=evidence_text,
                selected_tool=state.get("selected_tool"),
                tool_input=state.get("tool_input", {}),
                tool_result=state.get("tool_result", {}),
                current_tool_context=state.get("current_tool_context", {}),
                execution_plan=state.get("execution_plan", {}),
                task_results=state.get("task_results", []),
                completion_assessment=state.get("completion_assessment", {}),
            )
            answer = self._invoke_text(
                state=state,
                node="generate_answer",
                system=GENERATE_ANSWER_SYSTEM,
                user=user_prompt,
                llm=self.answer_llm,
                model_name=self.settings.qwen_chat_model,
            )
            state["final_answer"] = answer.strip() or "抱歉，我暂时无法生成回答。"
        return state

    def stream_generate_answer(self, state: AgentState):
        with NodeTimer(state, "generate_answer"):
            if state.get("route") == "reject":
                state["final_answer"] = state.get("final_answer") or "抱歉，这个请求存在安全风险，我不能执行。"
                yield state["final_answer"]
                return
            if state.get("route") == "direct" and state.get("intent") == "smalltalk":
                state["final_answer"] = state.get("final_answer") or "你好，我是企业知识库助手。你可以问我公司制度、考勤、公司日程等问题。"
                yield state["final_answer"]
                return
            if state.get("route") == "direct" and state.get("intent") == "permission_required":
                state["final_answer"] = state.get("final_answer") or self._permission_required_direct_answer(state)
                yield state["final_answer"]
                return

            evidence_text = state.get("evidence_brief") or compact_evidence_text(state.get("retrieved_docs", []), entities=state.get("entities", []))
            user_prompt = format_answer_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                route=state.get("route", "direct"),
                model_name=self.settings.qwen_chat_model,
                evidence_assessment=state.get("evidence_assessment", {}),
                evidence_text=evidence_text,
                selected_tool=state.get("selected_tool"),
                tool_input=state.get("tool_input", {}),
                tool_result=state.get("tool_result", {}),
                current_tool_context=state.get("current_tool_context", {}),
                execution_plan=state.get("execution_plan", {}),
                task_results=state.get("task_results", []),
                completion_assessment=state.get("completion_assessment", {}),
            )

            start = time.perf_counter()
            chunks: list[str] = []
            llm = self.answer_llm
            if hasattr(llm, "stream"):
                for chunk in llm.stream([("system", GENERATE_ANSWER_SYSTEM), ("user", user_prompt)]):
                    content = get_message_content(chunk)
                    if not content:
                        continue
                    chunks.append(content)
                    yield content
                answer = "".join(chunks).strip()
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                state.setdefault("llm_calls", []).append(
                    {
                        "node": "generate_answer",
                        "model": self.settings.qwen_chat_model,
                        "prompt_chars": len(GENERATE_ANSWER_SYSTEM) + len(user_prompt),
                        "output_chars": len(answer),
                        "latency_ms": elapsed_ms,
                        "streaming": True,
                    }
                )
            else:
                answer = self._invoke_text(
                    state=state,
                    node="generate_answer",
                    system=GENERATE_ANSWER_SYSTEM,
                    user=user_prompt,
                    llm=llm,
                    model_name=self.settings.qwen_chat_model,
                ).strip()
                if answer:
                    yield answer
            state["final_answer"] = answer or "抱歉，我暂时无法生成回答。"

    def update_memory(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "update_memory"):
            answer = state.get("final_answer", "")
            old_summary = state.get("conversation_summary", "")
            route = state.get("route", "direct")

            should_use_lightweight_memory = self._should_use_lightweight_memory(state)
            if should_use_lightweight_memory:
                memory_answer = strip_citations_and_metadata(answer)
                topic = state.get("topic", "")
                entities = state.get("entities", [])
                summary = old_summary or ""
            else:
                user_prompt = format_memory_user(
                    question=state.get("question", ""),
                    standalone_query=state.get("standalone_query", ""),
                    answer=truncate(answer, 1600),
                    old_summary=old_summary,
                )
                payload = self._invoke_json(
                    state=state,
                    node="update_memory",
                    system=MEMORY_UPDATE_SYSTEM,
                    user=user_prompt,
                    default={
                        "memory_answer": strip_citations_and_metadata(answer),
                        "summary": old_summary,
                        "topic": state.get("topic", ""),
                        "entities": state.get("entities", []),
                    },
                )
                memory_answer = str(payload.get("memory_answer") or strip_citations_and_metadata(answer))
                summary = str(payload.get("summary") or old_summary)
                topic = str(payload.get("topic") or state.get("topic", ""))
                entities = [str(x) for x in coerce_list(payload.get("entities") or state.get("entities", []))]

            state["memory_update"] = {
                "memory_answer": memory_answer,
                "summary": summary,
                "topic": topic,
                "entities": entities,
            }
            session_id = state.get("session_id")
            if session_id:
                self.context_store.update_summary(session_id, summary)
                self.context_store.append_turn(
                    session_id=session_id,
                    question=state.get("question", ""),
                    standalone_query=state.get("standalone_query", state.get("question", "")),
                    answer=answer,
                    sources=state.get("sources", []),
                    trace=self.build_trace(state),
                    memory_answer=memory_answer,
                    intent=state.get("intent", ""),
                    topic=topic,
                    entities=entities,
                )
            self._role_policy_snapshots.pop(str(state.get("workflow_run_id") or state.get("trace_id") or id(state)), None)
        return state

    # ---------- routing helpers ----------
    def next_after_route(self, state: AgentState) -> str:
        route = state.get("route") or "rag"
        if route == "tool":
            return "call_tool"
        if route == "rag":
            return "plan_retrieval"
        return "generate_answer"

    def after_completion_reflect(self, state: AgentState) -> str:
        assessment = state.get("completion_assessment") or {}
        if not assessment.get("ready_to_answer"):
            route = state.get("route") or "rag"
            if route == "tool":
                return "call_tool"
            if route == "rag":
                return "plan_retrieval"
        return "generate_answer"

    def should_retrieve(self, state: AgentState) -> str:
        """Backward-compatible helper used by older tests."""
        route = state.get("route") or "rag"
        if route in {"direct", "reject", "tool"}:
            return "generate_answer"
        return "plan_retrieval"

    def after_retrieve(self, state: AgentState) -> str:
        if self._can_skip_reflection(state):
            return "generate_answer"
        return "reflect_evidence"

    def after_reflect(self, state: AgentState) -> str:
        pending = state.get("pending_search_tasks") or []
        max_rounds = max(1, int(getattr(self.settings, "agent_reflect_max_rounds", 1) or 1))
        if pending and int(state.get("reflect_round") or 0) < max_rounds:
            return "retrieve"
        return "generate_answer"

    # ---------- trace/result ----------
    def build_trace(self, state: AgentState) -> dict[str, Any]:
        return {
            "mode": "agentic_rag_langgraph",
            "trace_id": state.get("trace_id"),
            "user_id": state.get("user_id"),
            "role": state.get("role"),
            "question": state.get("question"),
            "session_id": state.get("session_id"),
            "workflow_run_id": state.get("workflow_run_id"),
            "requested_kbs": state.get("requested_kbs", []),
            "allowed_kbs": state.get("allowed_kbs", []),
            "used_kbs": state.get("used_kbs", []),
            "route": state.get("route"),
            "intent": state.get("intent"),
            "message_type": state.get("message_type"),
            "context_usage": state.get("context_usage"),
            "time_requirement": state.get("time_requirement", {}),
            "knowledge_requirement": state.get("knowledge_requirement", {}),
            "execution_plan": state.get("execution_plan", {}),
            "task_results": state.get("task_results", []),
            "completed_tasks": state.get("completed_tasks", []),
            "plan_validation": state.get("plan_validation", {}),
            "risk_level": state.get("risk_level"),
            "standalone_query": state.get("standalone_query"),
            "topic": state.get("topic"),
            "entities": state.get("entities", []),
            "search_tasks": state.get("search_tasks", []),
            "executed_queries": state.get("executed_queries", []),
            "evidence_brief_chars": len(state.get("evidence_brief", "") or ""),
            "evidence_assessment": state.get("evidence_assessment", {}),
            "completion_assessment": state.get("completion_assessment", {}),
            "skipped_reflection_reason": state.get("skipped_reflection_reason"),
            "node_trace": state.get("node_trace", []),
            "llm_calls": state.get("llm_calls", []),
            "total_latency_ms": round(sum(float(item.get("latency_ms") or 0) for item in state.get("node_trace", [])), 2),
            "candidate_tool": state.get("candidate_tool"),
            "selected_tool": state.get("selected_tool"),
            "selected_action": state.get("selected_action"),
            "tool_input": state.get("tool_input", {}),
            "tool_result": state.get("tool_result", {}),
            "previous_tool_context": state.get("previous_tool_context", {}),
            "current_tool_context": state.get("current_tool_context", {}),
            "time_reference": state.get("time_reference", {}),
            "needs_time_resolution": state.get("needs_time_resolution", False),
            "relative_time": state.get("relative_time"),
            "missing_required_slots": state.get("missing_required_slots", []),
            "tool_calls": state.get("tool_calls", []),
            "observations": state.get("observations", []),
            "audit_events": state.get("audit_events", []),
            "sources": state.get("sources", []),
            "answer": state.get("final_answer", ""),
            "error": state.get("error"),
        }

    # ---------- internals ----------
    def _get_role_policies(self, state: AgentState) -> Any:
        """Return role policies once per workflow run.

        Permission checks happen in several nodes. Re-reading the SQLite policy
        table on every node adds avoidable latency without increasing safety,
        because a single workflow run must be evaluated against one consistent
        permission snapshot. Each executor still performs its own permission
        assertion against this snapshot immediately before executing work.
        """

        key = str(state.get("workflow_run_id") or state.get("trace_id") or id(state))
        cached = self._role_policy_snapshots.get(key)
        if cached is not None:
            return cached
        role_policies = self.auth_store.list_role_policies()
        if len(self._role_policy_snapshots) > 128:
            self._role_policy_snapshots.pop(next(iter(self._role_policy_snapshots)), None)
        self._role_policy_snapshots[key] = role_policies
        return role_policies

    def _state_to_plan_payload(self, state: AgentState) -> dict[str, Any]:
        return {
            "message_type": state.get("message_type") or "business_question",
            "context_usage": state.get("context_usage") or "none",
            "intent": state.get("intent") or "rag_fact",
            "route": state.get("route") or "rag",
            "standalone_query": state.get("standalone_query") or state.get("question") or "",
            "topic": state.get("topic") or "",
            "entities": state.get("entities") or [],
            "risk_level": state.get("risk_level") or "low",
            "selected_tool": state.get("selected_tool"),
            "selected_action": state.get("selected_action"),
            "required_tools": state.get("required_tools") or [],
            "tool_input": state.get("tool_input") or {},
            "time_requirement": state.get("time_requirement") or state.get("time_reference") or {},
            "knowledge_requirement": state.get("knowledge_requirement") or {},
            "execution_plan": state.get("execution_plan") or {},
            "missing_required_slots": state.get("missing_required_slots") or [],
            "reason": state.get("query_reason") or "",
        }

    def _time_requirement_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload or {})
        value = payload.get("time_requirement") or payload.get("time_reference") or {}
        value = dict(value) if isinstance(value, dict) else {}

        for key in ("has_time_requirement", "time_reference_type", "canonical_relative", "absolute_date", "date_range"):
            if key in payload and key not in value:
                value[key] = payload.get(key)

        # Backward-compatible planner fields used by older tests/prompts.
        # The canonical contract is nested time_requirement, but accepting these
        # fields keeps validation schema-driven rather than relying on text rules.
        legacy_relative = str(payload.get("relative_time") or payload.get("canonical_relative") or "").strip()
        legacy_needs_datetime = bool(payload.get("needs_time_resolution") or payload.get("requires_current_datetime"))
        if legacy_relative and not value.get("canonical_relative"):
            value["canonical_relative"] = legacy_relative
        if legacy_needs_datetime:
            value["requires_current_datetime"] = True
            value["needs_current_datetime"] = True
            value["has_time_requirement"] = True
            if not value.get("time_reference_type") or value.get("time_reference_type") == "none":
                value["time_reference_type"] = "relative" if legacy_relative else "ambiguous"
        if payload.get("absolute_date") and not value.get("absolute_date"):
            value["absolute_date"] = payload.get("absolute_date")
            value.setdefault("time_reference_type", "absolute")
            value.setdefault("has_time_requirement", True)
        if isinstance(payload.get("date_range"), dict) and not value.get("date_range"):
            value["date_range"] = payload.get("date_range")
            value.setdefault("time_reference_type", "range")
            value.setdefault("has_time_requirement", True)
        return self._normalize_time_requirement(value)

    def _normalize_time_requirement(self, value: Any) -> dict[str, Any]:
        value = value if isinstance(value, dict) else {}
        time_type = str(value.get("time_reference_type") or "none")
        if time_type not in {"none", "relative", "absolute", "range", "ambiguous"}:
            time_type = "none"
        canonical = self._normalize_relative_range_key(str(value.get("canonical_relative") or "").strip()) or None
        if canonical not in CANONICAL_RELATIVE_RANGES:
            canonical = None
        date_range = value.get("date_range") if isinstance(value.get("date_range"), dict) else None
        requires_current = bool(value.get("requires_current_datetime") or value.get("needs_current_datetime"))
        # Relative time is defined by the current clock/date. Even when the
        # Planner cannot map it to a canonical range, execution must fetch
        # get_current_datetime and either resolve directly or run the validation
        # feedback loop. We do not trust dates guessed in the plan.
        if time_type == "relative":
            requires_current = True
        return {
            "has_time_requirement": bool(value.get("has_time_requirement") or time_type != "none"),
            "time_reference_type": time_type,
            "canonical_relative": canonical,
            "absolute_date": value.get("absolute_date") if time_type == "absolute" else None,
            "date_range": date_range if time_type == "range" else None,
            "requires_current_datetime": requires_current,
            # Legacy key used by older helpers.
            "needs_current_datetime": requires_current,
        }

    def _normalize_knowledge_requirement(self, value: Any) -> dict[str, Any]:
        value = value if isinstance(value, dict) else {}
        return {
            "requires_company_knowledge": bool(value.get("requires_company_knowledge")),
            "known_from_user_message": bool(value.get("known_from_user_message")),
            "should_use_rag": bool(value.get("should_use_rag")),
        }

    def _execution_plan_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        value = payload.get("execution_plan") if isinstance(payload.get("execution_plan"), dict) else {}
        raw_tasks = value.get("tasks") if isinstance(value.get("tasks"), list) else None
        if raw_tasks is None:
            raw_tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else None
        tasks = [self._normalize_execution_task(task, idx, payload) for idx, task in enumerate(raw_tasks or [])]
        tasks = [task for task in tasks if task.get("kind")]
        if not tasks:
            fallback = self._fallback_execution_task(payload)
            if fallback:
                tasks = [fallback]
        return {
            "tasks": tasks,
            "strategy": str(value.get("strategy") or payload.get("reason") or "").strip(),
        }

    def _normalize_execution_task(self, task: Any, idx: int, plan_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        task = task if isinstance(task, dict) else {}
        plan_payload = plan_payload or {}
        kind = str(task.get("kind") or task.get("route") or "").strip().lower()
        tool = str(task.get("tool") or task.get("tool_name") or task.get("selected_tool") or "").strip() or None
        action = str(task.get("action") or task.get("selected_action") or "").strip() or None
        if not kind:
            if tool:
                kind = "tool"
            elif task.get("query"):
                kind = "rag"
        if kind not in {"rag", "tool", "direct"}:
            kind = ""
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
        time_requirement = self._time_requirement_from_payload(task)
        if not time_requirement.get("has_time_requirement"):
            time_requirement = self._time_requirement_from_payload(plan_payload)
        normalized = {
            "task_id": str(task.get("task_id") or f"t{idx + 1}"),
            "kind": kind,
            "objective": str(task.get("objective") or task.get("standalone_query") or task.get("query") or "").strip(),
            "query": str(task.get("query") or task.get("standalone_query") or task.get("objective") or "").strip(),
            "tool": tool,
            "action": action,
            "tool_input": dict(tool_input),
            "time_requirement": time_requirement,
            "depends_on": [str(x) for x in coerce_list(task.get("depends_on"))],
        }
        if normalized["kind"] == "tool":
            normalized["query"] = ""
            if normalized["tool"] == "manage_company_calendar" and normalized["action"] and not normalized["tool_input"].get("action"):
                normalized["tool_input"]["action"] = normalized["action"]
        return {key: value for key, value in normalized.items() if value not in (None, "", [], {}) or key in {"task_id", "kind", "tool_input"}}

    def _fallback_execution_task(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        route = str(payload.get("route") or "direct")
        standalone = str(payload.get("standalone_query") or payload.get("question") or "").strip()
        selected_tool = str(payload.get("selected_tool") or "").strip()
        if selected_tool:
            action = str(payload.get("selected_action") or (payload.get("tool_input") or {}).get("action") or "").strip() or None
            tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
            return {
                "task_id": "t1",
                "kind": "tool",
                "objective": standalone or f"执行 {selected_tool}",
                "tool": selected_tool,
                "action": action,
                "tool_input": dict(tool_input),
                "time_requirement": self._time_requirement_from_payload(payload),
                "depends_on": [],
            }
        if route == "rag":
            return {
                "task_id": "t1",
                "kind": "rag",
                "objective": standalone or "查询企业知识库",
                "query": standalone,
                "tool_input": {},
                "time_requirement": self._time_requirement_from_payload(payload),
                "depends_on": [],
            }
        if route == "tool":
            tool = str(payload.get("selected_tool") or "").strip()
            if not tool:
                return None
            action = str(payload.get("selected_action") or (payload.get("tool_input") or {}).get("action") or "").strip() or None
            tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
            return {
                "task_id": "t1",
                "kind": "tool",
                "objective": standalone or f"执行 {tool}",
                "tool": tool,
                "action": action,
                "tool_input": dict(tool_input),
                "time_requirement": self._time_requirement_from_payload(payload),
                "depends_on": [],
            }
        if route == "direct" and payload.get("intent") not in {"smalltalk", "permission_required"}:
            return {
                "task_id": "t1",
                "kind": "direct",
                "objective": standalone or "直接回答",
                "tool_input": {},
                "time_requirement": self._time_requirement_from_payload(payload),
                "depends_on": [],
            }
        return None

    def _prime_next_task(self, state: AgentState) -> dict[str, Any] | None:
        """Move the next unfinished planned task into the explicit graph branch.

        The workflow no longer has a hidden queue executor node. This helper
        only maps one structured task at a time onto the normal RAG or tool
        branch, so node traces show the real execution path.
        """

        queue = [dict(task) for task in list(state.get("task_queue") or []) if isinstance(task, dict)]
        if not queue:
            return None
        completed = set(state.get("completed_tasks") or [])
        max_steps = max(1, int(getattr(self.settings, "agent_max_steps", 10) or 10))
        if len(completed) >= max_steps:
            state["task_queue"] = []
            return None
        while queue:
            task = dict(queue.pop(0))
            task_id = str(task.get("task_id") or f"t{len(completed) + 1}")
            task["task_id"] = task_id
            if task_id in completed:
                continue
            state["task_queue"] = queue
            state["current_task"] = task
            self._apply_execution_task_to_state(state, task)
            return task
        state["task_queue"] = []
        return None

    def _apply_execution_task_to_state(self, state: AgentState, task: dict[str, Any]) -> None:
        kind = str(task.get("kind") or "").lower()
        objective = str(task.get("objective") or "").strip()
        if kind == "tool":
            tool_name = str(task.get("tool") or "").strip()
            action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").strip() or None
            tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
            task_time = task.get("time_requirement") if isinstance(task.get("time_requirement"), dict) else {}
            time_requirement = self._normalize_time_requirement(task_time)
            state["route"] = "tool"
            state["intent"] = "daily_tool"
            state["selected_tool"] = tool_name or None
            state["selected_action"] = action
            state["required_tools"] = [tool_name] if tool_name else []
            state["tool_input"] = dict(tool_input)
            state["time_requirement"] = time_requirement
            state["time_reference"] = time_requirement
            state["needs_time_resolution"] = bool(time_requirement.get("requires_current_datetime"))
            state["relative_time"] = str(time_requirement.get("canonical_relative") or "") or None
            if objective:
                state["standalone_query"] = objective
            return

        if kind == "rag":
            query = str(task.get("query") or objective or state.get("standalone_query") or state.get("question") or "").strip()
            previous_intent = str(state.get("intent") or "")
            state["route"] = "rag"
            state["intent"] = previous_intent if previous_intent.startswith("rag_") else "rag_fact"
            state["standalone_query"] = query
            state["selected_tool"] = None
            state["selected_action"] = None
            state["required_tools"] = []
            state["tool_input"] = {}
            return

        state["route"] = "direct"
        if objective:
            state["standalone_query"] = objective

    def _record_tool_task_result(self, state: AgentState, before_tool_calls: int = 0) -> None:
        task = state.get("current_task") or {}
        if not isinstance(task, dict) or str(task.get("kind") or "").lower() != "tool":
            return
        task_id = str(task.get("task_id") or "")
        if not task_id or task_id in set(state.get("completed_tasks") or []):
            return
        result = dict(state.get("tool_result") or {})
        tool_name = str(state.get("selected_tool") or task.get("tool") or "")
        action = str(state.get("selected_action") or task.get("action") or (state.get("tool_input") or {}).get("action") or "*")
        new_calls = list(state.get("tool_calls") or [])[max(0, before_tool_calls):]
        status = "error" if result.get("error") or state.get("error") else "ok"
        state.setdefault("task_results", []).append(
            {
                "task_id": task_id,
                "kind": "tool",
                "objective": task.get("objective") or tool_name,
                "status": status,
                "tool_name": tool_name,
                "action": action,
                "tool_input": {
                    key: value
                    for key, value in (state.get("tool_input") or {}).items()
                    if key not in {"query", "user_id", "role"}
                },
                "tool_result": result,
                "tool_calls": new_calls,
                "result_summary": self._format_tool_result(tool_name, result) if result else "",
                "error_message": state.get("final_answer") if status == "error" else "",
            }
        )
        state.setdefault("completed_tasks", []).append(task_id)

    def _record_rag_task_result(self, state: AgentState) -> None:
        task = state.get("current_task") or {}
        if not isinstance(task, dict) or str(task.get("kind") or "").lower() != "rag":
            return
        task_id = str(task.get("task_id") or "")
        if not task_id or task_id in set(state.get("completed_tasks") or []):
            return
        query = str(task.get("query") or task.get("objective") or state.get("standalone_query") or state.get("question") or "").strip()
        sources = list(state.get("sources") or [])
        state.setdefault("task_results", []).append(
            {
                "task_id": task_id,
                "kind": "rag",
                "objective": task.get("objective") or query,
                "status": "ok" if sources or state.get("retrieved_docs") else "no_evidence",
                "query": query,
                "executed_queries": list(state.get("executed_queries") or []),
                "sources": sources,
                "evidence_summary": truncate(state.get("evidence_brief") or "", 900),
            }
        )
        state.setdefault("completed_tasks", []).append(task_id)

    def _apply_plan_payload_to_state(self, state: AgentState, payload: dict[str, Any], normalize: bool = False) -> None:
        question = state.get("question", "")
        payload = dict(payload or {})
        time_requirement = self._time_requirement_from_payload(payload)
        knowledge_requirement = self._normalize_knowledge_requirement(payload.get("knowledge_requirement") or {})
        route = str(payload.get("route") or "rag")
        if route not in {"direct", "rag", "tool", "reject"}:
            route = "rag"
        selected_tool = str(payload.get("selected_tool") or "") or None
        selected_action = str(payload.get("selected_action") or (payload.get("tool_input") or {}).get("action") or "") or None
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        required_tools = [str(x) for x in coerce_list(payload.get("required_tools"))]
        if route == "tool" and selected_tool and selected_tool not in required_tools:
            required_tools = [selected_tool]
        execution_plan = self._execution_plan_from_payload(payload)
        state["message_type"] = str(payload.get("message_type") or "business_question")
        state["context_usage"] = str(payload.get("context_usage") or "none")
        state["intent"] = str(payload.get("intent") or "rag_fact")
        state["route"] = route  # type: ignore[assignment]
        state["risk_level"] = str(payload.get("risk_level") or "low")
        state["standalone_query"] = str(payload.get("standalone_query") or question).strip() or question
        state["topic"] = str(payload.get("topic") or "")
        state["entities"] = dedupe_keep_order([str(x).strip() for x in coerce_list(payload.get("entities")) if str(x).strip()])
        state["selected_tool"] = selected_tool
        state["selected_action"] = selected_action
        state["required_tools"] = required_tools
        state["tool_input"] = tool_input
        state["execution_plan"] = execution_plan
        state["task_queue"] = list(execution_plan.get("tasks") or [])
        state["time_requirement"] = time_requirement
        state["knowledge_requirement"] = knowledge_requirement
        state["time_reference"] = time_requirement  # legacy compatibility
        state["needs_time_resolution"] = bool(time_requirement.get("requires_current_datetime"))
        state["relative_time"] = str(time_requirement.get("canonical_relative") or "") or None
        state["missing_required_slots"] = [str(x) for x in coerce_list(payload.get("missing_required_slots"))]
        state["query_reason"] = str(payload.get("reason") or "")
        state["router_reason"] = str(payload.get("reason") or "")
        self._prime_next_task(state)

    def _normalize_planner_contract(
        self,
        payload: dict[str, Any],
        role: str,
        role_policies: Any | None = None,
        state: AgentState | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        payload["time_requirement"] = self._time_requirement_from_payload(payload)
        payload["knowledge_requirement"] = self._normalize_knowledge_requirement(payload.get("knowledge_requirement") or {})

        message_type = str(payload.get("message_type") or "business_question")
        route = str(payload.get("route") or "rag")
        selected_tool = str(payload.get("selected_tool") or "") or None
        selected_action = str(payload.get("selected_action") or (payload.get("tool_input") or {}).get("action") or "") or None
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        raw_execution_plan = payload.get("execution_plan") if isinstance(payload.get("execution_plan"), dict) else {}
        raw_tasks = raw_execution_plan.get("tasks") if isinstance(raw_execution_plan.get("tasks"), list) else payload.get("tasks")
        has_explicit_tasks = bool(raw_tasks)
        payload["execution_plan"] = self._execution_plan_from_payload(payload)
        tasks = list((payload.get("execution_plan") or {}).get("tasks") or [])

        if has_explicit_tasks and tasks and route == "direct" and message_type != "smalltalk":
            route = "tool" if any(task.get("kind") == "tool" for task in tasks) else "rag"
            payload["route"] = route
        first_tool_task = next((task for task in tasks if task.get("kind") == "tool" and task.get("tool")), None)
        if first_tool_task and not selected_tool:
            selected_tool = str(first_tool_task.get("tool") or "") or None
            selected_action = selected_action or str(first_tool_task.get("action") or "") or None
            payload["selected_tool"] = selected_tool
            payload["selected_action"] = selected_action
            tool_input = first_tool_task.get("tool_input") if isinstance(first_tool_task.get("tool_input"), dict) else tool_input
            payload["tool_input"] = tool_input

        if message_type == "smalltalk":
            payload.update(
                {
                    "context_usage": "none",
                    "intent": "smalltalk",
                    "route": "direct",
                    "selected_tool": None,
                    "selected_action": None,
                    "tool_input": {},
                    "required_tools": [],
                    "execution_plan": {"tasks": [], "strategy": ""},
                    "normalization_reason": "smalltalk clears tool plan",
                }
            )
            return payload

        knowledge_requirement = payload.get("knowledge_requirement") or {}
        if knowledge_requirement.get("should_use_rag") and not has_explicit_tasks:
            payload.update(
                {
                    "intent": "rag_fact" if payload.get("intent") in {None, "", "daily_tool"} else payload.get("intent"),
                    "route": "rag",
                    "selected_tool": None,
                    "selected_action": None,
                    "tool_input": {},
                    "required_tools": [],
                    "normalization_reason": "knowledge requirement routes to rag",
                }
            )
            return payload

        if selected_tool == "search_knowledge_base":
            payload["route"] = "rag"
            payload["selected_tool"] = None
            payload["selected_action"] = None
            payload["tool_input"] = {}
            payload["required_tools"] = []
            payload.setdefault("normalization_reason", "search knowledge base is rag route")
            return payload

        previous_context = (state or {}).get("previous_tool_context") if state is not None else {}
        planning_context = (state or {}).get("planning_context") if state is not None else {}
        if not previous_context and isinstance(planning_context, dict):
            previous_context = planning_context.get("previous_tool_context") or {}
        previous_context = previous_context if isinstance(previous_context, dict) else {}
        previous_input = previous_context.get("tool_input") if isinstance(previous_context.get("tool_input"), dict) else {}
        if (
            str(payload.get("context_usage") or "") == "use_previous_tool_context"
            and not selected_tool
            and previous_context.get("tool_name")
        ):
            selected_tool = str(previous_context.get("tool_name") or "") or None
            inherited_input = dict(previous_input)
            inherited_input.update(tool_input)
            tool_input = inherited_input
            selected_action = selected_action or str(tool_input.get("action") or "") or None
            payload.update(
                {
                    "route": "tool",
                    "intent": "daily_tool" if payload.get("intent") in {None, "", "direct"} else payload.get("intent"),
                    "selected_tool": selected_tool,
                    "selected_action": selected_action,
                    "tool_input": tool_input,
                    "required_tools": [selected_tool] if selected_tool else [],
                    "normalization_reason": "previous tool context requires executable tool plan",
                }
            )
            fallback_task = self._fallback_execution_task(payload)
            payload["execution_plan"] = {"tasks": [fallback_task] if fallback_task else [], "strategy": str(payload.get("reason") or "")}
            route = "tool"

        if selected_tool and route == "direct":
            # A planner output that names a visible tool but still says direct is
            # structurally inconsistent. Normalize by contract fields, not by
            # message keywords. Permission is still checked below and again at
            # execution time.
            payload["route"] = "tool"
            payload.setdefault("normalization_reason", "selected tool implies tool route")
            fallback_task = self._fallback_execution_task(payload)
            payload["execution_plan"] = {"tasks": [fallback_task] if fallback_task else [], "strategy": str(payload.get("reason") or "")}
            route = "tool"

        if route == "rag":
            payload["route"] = "rag"
            payload["selected_tool"] = None
            payload["selected_action"] = None
            payload["tool_input"] = {}
            return payload

        if route == "tool":
            if not selected_tool or not self.tool_registry.has_tool(selected_tool):
                payload.update(
                    {
                        "route": "direct",
                        "intent": "permission_required",
                        "selected_tool": None,
                        "selected_action": None,
                        "tool_input": {},
                        "required_tools": [],
                        "execution_plan": {"tasks": [], "strategy": ""},
                        "normalization_reason": "selected tool not visible",
                    }
                )
                return payload
            allowed_actions = self.tool_registry.allowed_actions(selected_tool, role, role_policies=role_policies)
            action_for_check = selected_action or "*"
            if "*" not in allowed_actions and action_for_check not in allowed_actions:
                payload.update(
                    {
                        "route": "direct",
                        "intent": "permission_required",
                        "selected_tool": None,
                        "selected_action": None,
                        "tool_input": {},
                        "required_tools": [],
                        "execution_plan": {"tasks": [], "strategy": ""},
                        "normalization_reason": "selected action not visible",
                    }
                )
                return payload
            payload["selected_tool"] = selected_tool
            payload["selected_action"] = selected_action or ("*" if "*" in allowed_actions else None)
            payload["required_tools"] = [selected_tool]
            if selected_tool == "manage_company_calendar" and payload.get("selected_action"):
                tool_input = dict(tool_input)
                tool_input["action"] = payload.get("selected_action")
                # Contract-level semantics: event_type is a filter. If the planner
                # declares a broad query scope, make the executable filter explicit.
                if tool_input.get("query_scope") == "all_events":
                    tool_input["event_type"] = "all"
                payload["tool_input"] = tool_input
            return payload

        if route not in {"direct", "reject"}:
            payload["route"] = "direct"
        return payload

    def _finalize_tool_input_with_llm(
        self,
        state: AgentState,
        tool_name: str,
        payload: dict[str, Any],
        datetime_result: dict[str, Any] | None = None,
        validation_error: str | None = None,
    ) -> dict[str, Any]:
        tool = self.tool_registry.get(tool_name)
        input_schema = tool.input_schema if tool else {}

        user_prompt = "\n\n".join(
            [
                f"current_message：{state.get('question', '')}",
                f"standalone_query：{state.get('standalone_query', state.get('question', ''))}",
                f"selected_tool：{tool_name}",
                f"selected_action：{state.get('selected_action') or ''}",
                "time_reference：" + self._safe_json_dumps(state.get("time_reference", {})),
                "tool_input_draft：" + self._safe_json_dumps(payload),
                "previous_tool_context：" + self._safe_json_dumps(state.get("previous_tool_context", {})),
                "current_datetime_result：" + self._safe_json_dumps(datetime_result or {}),
                f"validation_error：{validation_error or '无'}",
                "input_schema：" + self._safe_json_dumps(input_schema),
                "action_field_contract：manage_company_calendar.query 使用 start_date/end_date；manage_company_calendar.create/update 使用 date；delete 使用 event_id。",
                "如果当前消息包含相对日期，请只基于 current_datetime_result 推导日期，不要凭模型常识猜当前日期。",
                "weekday_derivation：如果 current_datetime_result.ranges.next_week 存在，则 next_week.start_date 是周一；周二 = start_date + 1 天，周三 = start_date + 2 天，周四 = start_date + 3 天，周五 = start_date + 4 天，周六 = start_date + 5 天，周日 = start_date + 6 天。",
                "同理 this_week、last_week、week_after_next 的 start_date 都是该周周一。遇到“下周二/本周五/上周三”必须按对应周范围和星期偏移计算 date。",
                "只输出修正后的 JSON tool_input，严格符合 selected_action 的字段契约，不要解释。",
            ]
        )

        fixed = self._invoke_json(
            state=state,
            node="finalize_tool_input",
            system="你是企业工具参数修复器。你只能输出严格 JSON。根据 selected_action、time_reference、日期工具结果和 input_schema 生成可执行 tool_input；不要回答用户。",
            user=user_prompt,
            default=payload,
        )
        return fixed if isinstance(fixed, dict) else payload

    def _build_tool_payload(self, state: AgentState, tool_name: str, role: str) -> dict[str, Any]:
        payload = dict(state.get("tool_input") or {})
        time_reference = self._time_reference_from_state(state)
        datetime_result: dict[str, Any] | None = None

        if tool_name == "get_current_datetime":
            payload.setdefault("timezone", "Asia/Shanghai")
            payload = validate_tool_input(tool_name, payload)
            payload.update({"query": state.get("question", ""), "user_id": state.get("user_id"), "role": role})
            return payload

        self._apply_time_reference_directly(tool_name, payload, time_reference)

        if str(time_reference.get("time_reference_type") or "") == "relative":
            # For relative time, concrete dates in the Planner output may be
            # guessed. Remove them and rebuild from get_current_datetime or the
            # validation feedback loop.
            action = str(payload.get("action") or state.get("selected_action") or "query").lower()
            if tool_name in {"query_attendance_summary", "manage_company_calendar"} and action == "query":
                payload.pop("start_date", None)
                payload.pop("end_date", None)
            if tool_name == "manage_company_calendar" and action in {"create", "update"}:
                payload.pop("date", None)

        if time_reference.get("needs_current_datetime") or time_reference.get("requires_current_datetime"):
            datetime_result = self._run_datetime_for_tool(state, role)
            self._apply_datetime_range_if_possible(state, tool_name, payload, datetime_result)

        runtime_extras = {key: payload[key] for key in ("file_path",) if key in payload}
        self._normalize_tool_payload_for_action_contract(tool_name, payload, state=state)
        try:
            payload = validate_tool_input(tool_name, payload)
        except ValidationError as exc:
            payload = self._finalize_tool_input_with_llm(
                state=state,
                tool_name=tool_name,
                payload=payload,
                datetime_result=datetime_result,
                validation_error=str(exc),
            )
            self._normalize_tool_payload_for_action_contract(tool_name, payload, state=state)
            runtime_extras.update({key: payload[key] for key in ("file_path",) if key in payload})
            payload = validate_tool_input(tool_name, payload)
        payload = self._prune_tool_payload_for_action_contract(tool_name, payload)
        payload.update(runtime_extras)

        payload.update({"query": state.get("question", ""), "user_id": state.get("user_id"), "role": role})
        return payload

    def _time_reference_from_state(self, state: AgentState) -> dict[str, Any]:
        time_reference = state.get("time_reference") or state.get("time_requirement") or {}
        if isinstance(time_reference, dict) and time_reference:
            merged = dict(time_reference)
        else:
            merged = {}
        relative_time = str(state.get("relative_time") or "").strip()
        if relative_time and not merged.get("canonical_relative"):
            merged["canonical_relative"] = relative_time
        if state.get("needs_time_resolution"):
            merged["has_time_requirement"] = True
            merged["requires_current_datetime"] = True
            merged["needs_current_datetime"] = True
            if not merged.get("time_reference_type") or merged.get("time_reference_type") == "none":
                merged["time_reference_type"] = "relative" if relative_time else "ambiguous"
        normalized = self._normalize_time_requirement(merged)
        state["time_reference"] = normalized
        state["time_requirement"] = normalized
        state["needs_time_resolution"] = bool(normalized.get("requires_current_datetime"))
        state["relative_time"] = str(normalized.get("canonical_relative") or "") or None
        return normalized

    def _apply_time_reference_directly(self, tool_name: str, payload: dict[str, Any], time_reference: dict[str, Any]) -> None:
        time_type = str(time_reference.get("time_reference_type") or "none")
        if time_type == "absolute" and time_reference.get("absolute_date"):
            day = str(time_reference.get("absolute_date"))
            if tool_name in {"query_attendance_summary", "manage_company_calendar"} and str(payload.get("action") or "query") == "query":
                payload.setdefault("start_date", day)
                payload.setdefault("end_date", day)
            elif tool_name == "manage_company_calendar":
                payload.setdefault("date", day)
        elif time_type == "range" and isinstance(time_reference.get("date_range"), dict):
            date_range = time_reference.get("date_range") or {}
            if tool_name in {"query_attendance_summary", "manage_company_calendar"}:
                payload.setdefault("start_date", date_range.get("start_date"))
                payload.setdefault("end_date", date_range.get("end_date"))

    def _run_datetime_for_tool(self, state: AgentState, role: str) -> dict[str, Any]:
        assert_tool_action_permission(role, "get_current_datetime", "*", role_policies=self._get_role_policies(state))
        datetime_payload = {"timezone": "Asia/Shanghai"}
        datetime_result = get_current_datetime(datetime_payload)
        state.setdefault("tool_calls", []).append(
            {
                "tool_name": "get_current_datetime",
                "action": "*",
                "args": datetime_payload,
                "ok": not bool(datetime_result.get("error")),
                "risk_level": "low",
                "purpose": "resolve_time_reference",
            }
        )
        state.setdefault("observations", []).append({"type": "tool", "tool_name": "get_current_datetime", "result": datetime_result})
        state.setdefault("audit_events", []).append({"event": "tool_call", "tool_name": "get_current_datetime", "role": role, "decision": "allowed"})
        return datetime_result

    def _apply_datetime_range_if_possible(
        self,
        state: AgentState,
        tool_name: str,
        payload: dict[str, Any],
        datetime_result: dict[str, Any] | None,
    ) -> None:
        time_reference = state.get("time_reference") or {}
        range_key = self._normalize_relative_range_key(
            str(time_reference.get("canonical_relative") or state.get("relative_time") or payload.get("relative_time") or "").strip()
        )
        if not range_key or not datetime_result:
            return
        selected_range = (datetime_result.get("ranges") or {}).get(range_key) or {}
        if not selected_range:
            return

        start_date = selected_range.get("start_date")
        end_date = selected_range.get("end_date")

        if tool_name == "query_attendance_summary":
            payload["start_date"] = start_date
            payload["end_date"] = end_date
            payload["_relative_range"] = range_key
            return

        if tool_name == "manage_company_calendar":
            action = str(payload.get("action") or state.get("selected_action") or "query").lower()
            if action == "query":
                payload["start_date"] = start_date
                payload["end_date"] = end_date
                if not payload.get("query_scope"):
                    payload["query_scope"] = "all_events" if str(payload.get("event_type") or "all") == "all" else "type_filtered"
                if payload.get("query_scope") == "all_events":
                    payload["event_type"] = "all"
                payload.setdefault("department", "all")
                payload["_relative_range"] = range_key
                return
            if action in {"create", "update"} and start_date == end_date:
                payload.setdefault("date", start_date)
                payload["_relative_range"] = range_key

    @staticmethod
    def _normalize_tool_payload_for_action_contract(tool_name: str, payload: dict[str, Any], state: AgentState | None = None) -> None:
        """Align cross-stage payloads with the selected tool/action contract.

        Planner and finalizer stages may use range-shaped fields while a write
        action needs a single date. This helper performs schema-level coercion
        only; it does not infer business semantics from the user text.
        """

        if tool_name != "manage_company_calendar":
            return
        action = str(payload.get("action") or (state or {}).get("selected_action") or "query").strip().lower() or "query"
        payload["action"] = action
        if action not in {"create", "update", "delete"}:
            return
        start_date = str(payload.get("start_date") or "").strip()
        end_date = str(payload.get("end_date") or "").strip()
        if not payload.get("date") and start_date and start_date == end_date:
            payload["date"] = start_date
        for query_field in ("start_date", "end_date", "query_scope", "event_type"):
            payload.pop(query_field, None)

    @staticmethod
    def _prune_tool_payload_for_action_contract(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "manage_company_calendar":
            return payload
        action = str(payload.get("action") or "query").strip().lower() or "query"
        if action == "query":
            allowed = {"action", "start_date", "end_date", "query_scope", "event_type", "department"}
        elif action == "create":
            allowed = {"action", "title", "type", "date", "time", "department", "location", "description"}
        elif action == "update":
            allowed = {"action", "event_id", "title", "type", "date", "time", "department", "location", "description"}
        elif action == "delete":
            allowed = {"action", "event_id"}
        else:
            return payload
        return {key: value for key, value in payload.items() if key in allowed}

    @staticmethod
    def _safe_json_dumps(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            return str(value)

    @staticmethod
    def _normalize_relative_range_key(value: str) -> str:
        value = str(value or "").strip()
        return RELATIVE_RANGE_ALIASES.get(value, value)

    @staticmethod
    def _friendly_tool_error(tool_name: str, result: dict[str, Any], role: str | None = None, action: str | None = None) -> str:
        error = str(result.get("error") or "")
        action = str(action or result.get("action") or "")
        if tool_name == "manage_company_calendar" and error == "permission denied" and action in {"create", "update", "delete"}:
            return "你没有权限修改公司日程。只有 admin 可以新增、更新或删除日程。"
        if error == "invalid date format":
            if tool_name == "query_attendance_summary":
                return "我需要一个明确的日期范围才能查询考勤。你可以说“昨天”、“上周”或“2026-05-01 到 2026-05-07”。"
            if tool_name == "manage_company_calendar":
                return "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"
        return "工具执行失败，请检查请求参数后再试。"

    @staticmethod
    def _friendly_tool_validation_error(tool_name: str, exc: ValidationError) -> str:
        detail = str(exc)
        if tool_name == "query_attendance_summary" and any(field in detail for field in ("start_date", "end_date")):
            return "我需要一个明确的日期范围才能查询考勤。你可以说“昨天”、“上周”或“2026-05-01 到 2026-05-07”。"
        if tool_name == "manage_company_calendar" and any(field in detail for field in ("start_date", "end_date")):
            return "我需要一个明确的日期范围才能查询公司日程。你可以说“今天”、“下周”或具体日期范围。"
        if tool_name == "manage_company_calendar" and "title" in detail:
            return "我还缺少日程标题，请补充要新增或更新的日程名称。"
        if tool_name == "manage_company_calendar" and "event_id" in detail:
            return "我还缺少要修改或删除的日程 ID。"
        return "我还缺少执行该能力所需的必要信息，请补充具体日期、时间或事件信息。"


    @staticmethod
    def _friendly_permission_answer(role: str, tool_name: str, action: str | None = None) -> str:
        action = str(action or "*").lower()
        if tool_name == "manage_company_calendar" and action == "query":
            return "你当前角色无法查看公司内部日程，请使用员工或管理员账号登录后再查询。"
        if tool_name == "manage_company_calendar" and action in {"create", "update", "delete"}:
            return "你没有权限修改公司日程。只有 admin 可以新增、更新或删除日程。"
        if tool_name == "query_attendance_summary":
            return "你当前角色无法查看公司内部考勤数据，请使用员工或管理员账号登录后再查询。"
        return "你当前角色没有权限使用该企业能力。"

    @staticmethod
    def _permission_required_direct_answer(state: AgentState) -> str:
        topic = str(state.get("topic") or "").lower()
        standalone = str(state.get("standalone_query") or state.get("question") or "")
        text = f"{topic} {standalone}"
        if "calendar_write" in topic:
            return "你没有权限修改公司日程。只有 admin 可以新增、更新或删除日程。"
        if "calendar" in topic or "日程" in text:
            return "你当前角色无法查看公司内部日程，请使用员工或管理员账号登录后再查询。"
        if "attendance" in topic or "考勤" in text:
            return "你当前角色无法查看公司内部考勤数据，请使用员工或管理员账号登录后再查询。"
        return "你当前角色无权使用该企业能力，请切换到有权限的账号后再试。"

    def _build_current_tool_context(self, tool_name: str, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        domain = {
            "query_attendance_summary": "attendance",
            "manage_company_calendar": "calendar",
            "get_current_datetime": "datetime",
        }.get(tool_name, "tool")
        clean_input = {
            key: value
            for key, value in payload.items()
            if key not in {"file_path", "query", "user_id", "role"} and not str(key).startswith("_")
        }
        return {
            "domain": domain,
            "tool_name": tool_name,
            "tool_input": clean_input,
            "result_summary": self._summarize_tool_result(tool_name, result),
            "trace_id": None,
        }

    def _summarize_tool_result(self, tool_name: str, result: dict[str, Any]) -> str:
        return self._format_tool_result(tool_name, result)

    @staticmethod
    def _format_tool_result(tool_name: str, result: dict[str, Any]) -> str:
        if result.get("error"):
            return f"工具调用失败：{result.get('error')}"
        if tool_name == "get_current_datetime":
            return f"当前日期：{result.get('current_date')}，时间：{result.get('current_time')}，星期：{result.get('weekday')}，时区：{result.get('timezone')}。"
        if tool_name == "query_attendance_summary":
            status_filter = result.get("status_filter") or (result.get("filters") or {}).get("status_filter")
            filtered_count = result.get("filtered_count")
            records = result.get("records") or []
            if status_filter:
                status_label = {
                    "present": "正常出勤",
                    "late": "迟到",
                    "leave": "请假",
                    "absent": "缺勤",
                }.get(str(status_filter), str(status_filter))
                if records:
                    people: list[str] = []
                    for record in records[:8]:
                        detail = str(record.get("name") or "").strip()
                        department = str(record.get("department") or "").strip()
                        check_in = str(record.get("check_in") or "").strip()
                        if department:
                            detail += f"（{department}"
                            if check_in:
                                detail += f"，打卡 {check_in}"
                            detail += "）"
                        elif check_in:
                            detail += f"（打卡 {check_in}）"
                        if detail:
                            people.append(detail)
                    suffix = "；".join(people)
                    if len(records) > 8:
                        suffix += f" 等 {len(records)} 条记录"
                    return f"{result.get('start_date')} 至 {result.get('end_date')} 共有 {filtered_count} 条{status_label}记录：{suffix}。"
                return f"{result.get('start_date')} 至 {result.get('end_date')} 共有 {filtered_count or 0} 条{status_label}记录。"
            summary = result.get("summary") or {}
            return (
                f"{result.get('start_date')} 至 {result.get('end_date')} 的考勤汇总："
                f"记录 {summary.get('total_records', 0)} 条，出勤 {summary.get('present', 0)}，"
                f"迟到 {summary.get('late', 0)}，请假 {summary.get('leave', 0)}，缺勤 {summary.get('absent', 0)}，"
                f"出勤率 {summary.get('attendance_rate', '0.00%')}，迟到率 {summary.get('late_rate', '0.00%')}。"
            )
        if tool_name == "manage_company_calendar":
            action = result.get("action")
            if action == "query":
                events = result.get("events") or []
                if not events:
                    return f"{result.get('start_date')} 至 {result.get('end_date')} 暂无公司日程。"
                lines = [f"{result.get('start_date')} 至 {result.get('end_date')} 的公司日程："]
                for event in events:
                    lines.append(f"- {event.get('date')} {event.get('time')} {event.get('title')}（{event.get('location') or '未指定地点'}）")
                return "\n".join(lines)
            return str(result.get("message") or f"公司日程已{result.get('status', '处理')}")
        return str(result)

    def _get_retriever(self) -> Any:
        if self.retriever is None:
            from mini_rag.retrieval.retriever import KnowledgeBaseRetriever

            self.retriever = KnowledgeBaseRetriever(self.settings)
        return self.retriever

    def _invoke_text(
        self,
        state: AgentState,
        node: str,
        system: str,
        user: str,
        llm: Any | None = None,
        model_name: str | None = None,
    ) -> str:
        start = time.perf_counter()
        message = (llm or self.control_llm).invoke([("system", system), ("user", user)])
        content = get_message_content(message)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        state.setdefault("llm_calls", []).append(
            {
                "node": node,
                "model": model_name or self.settings.qwen_control_model or self.settings.qwen_chat_model,
                "prompt_chars": len(system) + len(user),
                "output_chars": len(content),
                "latency_ms": elapsed_ms,
            }
        )
        return content

    def _invoke_json(self, state: AgentState, node: str, system: str, user: str, default: dict[str, Any]) -> dict[str, Any]:
        raw = self._invoke_text(state=state, node=node, system=system, user=user, llm=self.control_llm)
        payload = safe_json_loads(raw, default=default)
        if not isinstance(payload, dict):
            return default
        return payload

    @staticmethod
    def _normalize_query_key(query: str) -> str:
        return " ".join(str(query or "").strip().split()).lower()

    @staticmethod
    def _is_dangerous_question(question: str, standalone_query: str) -> bool:
        text = f"{question} {standalone_query}".lower()
        risky_terms = ["api key", "apikey", "secret", "密钥", "泄露", "密码", "token"]
        return any(term in text for term in risky_terms)

    def _can_skip_reflection(self, state: AgentState) -> bool:
        if state.get("route") != "rag":
            return False
        if int(state.get("reflect_round") or 0) > 0 and state.get("retrieval_made_progress") is False:
            state["skipped_reflection_reason"] = "followup_retrieval_no_new_evidence"
            state.setdefault("evidence_assessment", {})
            state["evidence_assessment"].update(
                {
                    "can_answer_partial": bool(state.get("retrieved_docs")),
                    "followup_tasks": [],
                    "stop_reason": "followup_retrieval_no_new_evidence",
                    "reason": "补检索没有新增有效证据，继续检索收益低，进入回答阶段。",
                }
            )
            state["pending_search_tasks"] = []
            state.setdefault("observations", []).append(
                {"type": "evidence_reflection_skipped", "reason": state["skipped_reflection_reason"]}
            )
            return True
        if state.get("reflect_round"):
            return False
        docs = state.get("retrieved_docs") or []
        if not docs:
            return False
        executed_queries = state.get("executed_queries") or []
        task_count = len(state.get("search_tasks") or [])
        complex_multi_entity = (
            state.get("intent") in {"rag_explain", "rag_compare"}
            and len(state.get("entities") or []) > 1
        )
        if complex_multi_entity:
            return False
        if len(executed_queries) <= 1 and task_count <= 1:
            state["skipped_reflection_reason"] = "single_query_has_evidence"
            state["evidence_assessment"] = {
                "is_sufficient": True,
                "can_answer_partial": False,
                "missing_information": [],
                "followup_tasks": [],
                "reason": "单 query 已召回证据，跳过 LLM 证据反思以减少低价值耗时。",
            }
            state.setdefault("observations", []).append(
                {"type": "evidence_reflection_skipped", "reason": state["skipped_reflection_reason"]}
            )
            return True
        return False

    def _should_use_lightweight_memory(self, state: AgentState) -> bool:
        # Non-RAG routes already produce structured current_tool_context or
        # short direct answers. Avoid an extra LLM call on the hot path.
        if state.get("route") in {"tool", "direct", "reject"}:
            return True
        answer = state.get("final_answer", "")
        return len(answer) <= 1200

    def _optimize_search_tasks(self, state: AgentState, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Guard retrieval planning quality.

        ``plan_intent`` already produces a complete ``standalone_query``.
        Therefore the planning node must not broaden or rewrite the meaning
        again. For normal questions we use the standalone query directly. Only
        when the question is explicitly a comparison/multi-object request do we
        allow a few entity-specific tasks, and even then each task must stay
        anchored to the standalone query.
        """

        standalone_query = self._normalize_query_text(str(state.get("standalone_query") or state.get("question") or ""))
        entities = [str(x).strip() for x in state.get("entities", []) if str(x).strip()]
        intent = str(state.get("intent") or "")
        allow_split = intent in {"rag_compare", "rag_explain"} and len(entities) > 1

        optimized: list[dict[str, Any]] = []
        if not allow_split:
            optimized = [{"query": standalone_query, "purpose": "answer_question", "target_entity": None}]
        else:
            # Keep entity tasks narrow. Do not add new dimensions like “原理/优势/案例”
            # unless those words already appear in the standalone query.
            for task in tasks:
                query = self._normalize_query_text(str(task.get("query") or ""))
                target = str(task.get("target_entity") or "").strip() or None
                if not query:
                    continue
                # If the model generated an over-expanded query, fall back to
                # "standalone_query + target entity" instead of trusting it.
                if target and target not in query:
                    query = f"{standalone_query} {target}"
                if len(query) > max(len(standalone_query) + 40, 80):
                    query = f"{standalone_query} {target or ''}".strip()
                optimized.append({"query": query, "purpose": str(task.get("purpose") or "search"), "target_entity": target})
            if not optimized:
                optimized = [{"query": standalone_query, "purpose": "answer_question", "target_entity": None}]

        for task in optimized:
            task["query"] = self._normalize_query_text(str(task.get("query") or standalone_query))
            task.setdefault("top_k", self.settings.top_k)
            task.setdefault("candidate_k", self.settings.candidate_k)

        max_tasks = max(1, int(getattr(self.settings, "agent_max_search_tasks", 3) or 3))
        return dedupe_keep_order(optimized, key=lambda task: str(task.get("query")))[:max_tasks]

    @staticmethod
    def _normalize_query_text(query: str) -> str:
        return " ".join(str(query or "").strip().split())

    @staticmethod
    def _normalize_tasks(value: Any, fallback_query: str) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for item in coerce_list(value):
            if isinstance(item, str):
                item = {"query": item, "purpose": "search", "target_entity": None}
            if not isinstance(item, dict):
                continue
            query = str(item.get("query") or "").strip()
            if not query:
                continue
            task = {
                "query": query,
                "purpose": str(item.get("purpose") or "search"),
                "target_entity": item.get("target_entity"),
            }
            for opt_key in ("top_k", "candidate_k", "enable_rerank"):
                if opt_key in item:
                    task[opt_key] = item.get(opt_key)
            tasks.append(task)
        if not tasks and fallback_query:
            tasks = [{"query": fallback_query, "purpose": "answer_question", "target_entity": None}]
        return dedupe_keep_order(tasks, key=lambda task: str(task.get("query")))

    @staticmethod
    def _turn_to_history_item(turn: Any) -> dict[str, Any]:
        answer = getattr(turn, "memory_answer", "") or strip_citations_and_metadata(getattr(turn, "answer", ""))
        return {
            "question": getattr(turn, "question", ""),
            "standalone_query": getattr(turn, "standalone_query", ""),
            "answer": getattr(turn, "answer", ""),
            "memory_answer": answer,
            "intent": getattr(turn, "intent", ""),
            "topic": getattr(turn, "topic", ""),
            "entities": getattr(turn, "entities", []),
            "created_at": getattr(turn, "created_at", 0.0),
        }

    @staticmethod
    def _extract_previous_tool_context(turns: list[Any]) -> dict[str, Any]:
        """Return the latest compact tool context from persisted turn traces."""

        for turn in reversed(turns or []):
            trace = getattr(turn, "trace", {}) or {}
            if not isinstance(trace, dict):
                continue
            context = trace.get("current_tool_context") or trace.get("tool_context")
            if not isinstance(context, dict) or not context:
                continue
            tool_input = context.get("tool_input") if isinstance(context.get("tool_input"), dict) else {}
            compact_input = {
                str(key): value
                for key, value in tool_input.items()
                if str(key) not in {"file_path", "query", "user_id", "role"} and not str(key).startswith("_")
            }
            previous = {
                "domain": context.get("domain"),
                "tool_name": context.get("tool_name"),
                "tool_input": compact_input,
                "result_summary": str(context.get("result_summary") or "")[:700],
            }
            trace_id = context.get("trace_id") or trace.get("trace_id")
            if trace_id:
                previous["trace_id"] = trace_id
            return {key: value for key, value in previous.items() if value not in (None, "", {})}
        return {}


def create_initial_state(
    question: str,
    session_id: str | None = None,
    retrieval_mode: str | None = None,
    enable_rerank: bool | None = None,
    user_id: str | None = None,
    role: str | None = None,
    trace_id: str | None = None,
    kb_ids: list[str] | None = None,
) -> AgentState:
    workflow_run_id = uuid4().hex
    return {
        "question": question,
        "user_query": question,
        "session_id": session_id,
        "user_id": user_id or "anonymous",
        "role": normalize_role(role),
        "workflow_run_id": workflow_run_id,
        "trace_id": trace_id or workflow_run_id,
        "retrieval_mode": retrieval_mode,
        "enable_rerank": enable_rerank,
        "requested_kbs": kb_ids or [],
        "allowed_kbs": [],
        "used_kbs": [],
        "conversation_summary": "",
        "history": [],
        "intent": "",
        "message_type": "",
        "context_usage": "none",
        "available_tool_contracts": "[]",
        "planning_context": {},
        "raw_plan": {},
        "plan_validation": {},
        "execution_plan": {"tasks": []},
        "task_queue": [],
        "current_task": {},
        "task_results": [],
        "completed_tasks": [],
        "time_requirement": {},
        "knowledge_requirement": {},
        "prepared_tool_input": {},
        "route": "direct",
        "risk_level": "low",
        "standalone_query": question,
        "topic": "",
        "entities": [],
        "required_tools": [],
        "candidate_tool": None,
        "selected_tool": None,
        "selected_action": None,
        "tool_input": {},
        "tool_result": {},
        "previous_tool_context": {},
        "current_tool_context": {},
        "time_reference": {},
        "needs_time_resolution": False,
        "relative_time": None,
        "missing_required_slots": [],
        "search_tasks": [],
        "pending_search_tasks": [],
        "executed_queries": [],
        "_executed_query_keys": [],
        "_retrieval_cache": {},
        "retrieved_docs": [],
        "sources": [],
        "evidence_brief": "",
        "observations": [],
        "tool_calls": [],
        "evidence_assessment": {},
        "completion_assessment": {},
        "completion_reflect_round": 0,
        "reflect_round": 0,
        "final_answer": "",
        "memory_update": {},
        "node_trace": [],
        "llm_calls": [],
        "audit_events": [],
        "skipped_reflection_reason": None,
        "error": None,
    }
