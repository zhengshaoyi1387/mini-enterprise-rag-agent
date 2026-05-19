from __future__ import annotations

import json
import time
from typing import Any

from pydantic import ValidationError

from mini_rag.agent.context_store import SQLiteContextStore
from mini_rag.answer import build_current_tool_context as build_tool_context
from mini_rag.answer import format_tool_result
from mini_rag.answer.service import AnswerService
from mini_rag.answer.templates import friendly_permission_answer, friendly_tool_error, friendly_tool_validation_error
from mini_rag.capabilities.calendar.resolver import CalendarTaskResolver, is_unresolved_calendar_event_id
from mini_rag.capabilities.datetime.resolver import resolve_time_expression
from mini_rag.capabilities.datetime.service import build_time_context, datetime_payload_from_time_context, default_datetime_payload
from mini_rag.capabilities.rag.service import RAGRetrievalService
from mini_rag.capabilities.registry import default_capability_registry
from mini_rag.capabilities.verifier import verify_domain_tool_result
from mini_rag.config import Settings
from mini_rag.execution import execute_selected_tool
from mini_rag.execution.tool_input import build_tool_payload
from mini_rag.graph.prompts import (
    GENERATE_ANSWER_SYSTEM,
    PLAN_WITH_LLM_SYSTEM,
    REACT_NEXT_ACTION_SYSTEM,
    format_plan_with_llm_user,
    format_react_next_action_user,
)
from mini_rag.graph.state import AgentState
from mini_rag.graph.utils import NodeTimer, coerce_list, get_message_content, safe_json_loads
from mini_rag.memory.service import MemoryService
from mini_rag.observability.mainline_log import (
    append_mainline_step,
    summarize_answer,
    summarize_memory,
    summarize_plan,
    summarize_react_execution,
    summarize_runtime_context,
    summarize_time_resolution,
    summarize_validation,
)
from mini_rag.observability.trace_builder import TraceBuilder
from mini_rag.orchestration.react_executor import ReActExecutor, ReActExecutionResult, ReActGuardrailViolation
from mini_rag.orchestration.state_factory import create_initial_state
from mini_rag.orchestration.state_views import refresh_state_views
from mini_rag.planning.context_policy import build_context_packet
from mini_rag.planning.context_policy import extract_previous_tool_context, turn_to_history_item
from mini_rag.planning.gates import apply_capability_gates
from mini_rag.security.auth_store import SQLiteAuthStore
from mini_rag.security.permissions import assert_can_access_kbs, assert_tool_action_permission, normalize_role
from mini_rag.tools.daily_tools import build_default_tool_registry
from mini_rag.tools.datetime_tool import get_current_datetime


class AgenticRAGNodes:
    """Thin orchestration glue for the single enterprise-agent mainline.

    Runtime flow:
    TimeContext -> LLM Planner -> TimeResolver -> Validate/Gates ->
    ReActExecutor -> Tool/RAG -> Answer LLM -> Memory.
    """

    def __init__(self, settings: Settings, llm: Any | None = None, retriever: Any | None = None):
        self.settings = settings
        self.context_store = SQLiteContextStore(settings.context_db_path)
        if llm is None:
            from mini_rag.models.qwen import build_qwen_chat_model, build_qwen_control_model

            self.answer_llm = build_qwen_chat_model(settings)
            self.control_llm = build_qwen_control_model(settings)
        else:
            self.answer_llm = llm
            self.control_llm = llm
        self.llm = self.answer_llm
        self.retriever: Any | None = retriever
        self.tool_registry = build_default_tool_registry()
        self.capability_registry = default_capability_registry()
        self.auth_store = SQLiteAuthStore(settings.auth_db_path)
        self._role_policy_snapshots: dict[str, Any] = {}
        self.calendar_task_resolver = CalendarTaskResolver()
        self.rag_service = RAGRetrievalService(settings, self._get_retriever, self._get_role_policies, llm=self.control_llm)
        self.trace_builder = TraceBuilder(settings)
        self.answer_service = AnswerService(
            settings=settings,
            invoke_text=self._invoke_text,
            append_llm_call_trace=self._append_llm_call_trace,
            role_allowed_actions=self._role_allowed_actions_for_answer,
            answer_llm=self.answer_llm,
        )

    def build_runtime_context(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "build_runtime_context"):
            context = self.context_store.get_context(state.get("session_id"), max_turns=self.settings.session_max_turns)
            state["conversation_summary"] = context.summary
            state["history"] = [turn_to_history_item(turn) for turn in context.turns]
            state["previous_tool_context"] = extract_previous_tool_context(context.turns)
            for key, default in (
                ("observations", []),
                ("node_trace", []),
                ("tool_calls", []),
                ("retrieved_docs", []),
                ("sources", []),
                ("executed_queries", []),
                ("_executed_query_keys", []),
                ("_retrieval_cache", {}),
                ("llm_calls", []),
                ("task_results", []),
                ("completed_tasks", []),
                ("resolved_time_facts", []),
                ("react_steps", []),
            ):
                state.setdefault(key, default.copy() if isinstance(default, (list, dict)) else default)

            role = normalize_role(state.get("role"))
            role_policies = self._get_role_policies(state)
            try:
                allowed_kbs = assert_can_access_kbs(role, state.get("requested_kbs") or [], role_policies=role_policies)
            except PermissionError as exc:
                allowed_kbs = []
                state.update({"route": "reject", "risk_level": "medium", "error": str(exc), "final_answer": "你没有权限访问所请求的知识库。"})
            state["allowed_kbs"] = allowed_kbs
            state["used_kbs"] = allowed_kbs

            visible_capabilities = self.capability_registry.visible_contracts(role=role)
            tool_contracts = self.tool_registry.format_tool_contracts_for_prompt(role=role, role_policies=role_policies)
            tool_summary = self.tool_registry.format_tool_routing_summary_for_prompt(role=role, role_policies=role_policies)
            state["available_tool_contracts"] = tool_contracts
            state["available_tool_summary"] = tool_summary
            state["available_capabilities"] = [contract.name for contract in visible_capabilities]
            state["capability_catalog"] = {"capabilities": state["available_capabilities"], "tool_summary": tool_summary}
            state["permissions"] = {"role": role, "allowed_kbs": allowed_kbs, "tool_actions": self._role_allowed_actions_for_answer(state)}
            state["planning_context"] = build_context_packet(
                history=state.get("history") or [],
                previous_tool_context=state.get("previous_tool_context") or {},
            )

            ctx = build_time_context(
                timezone="Asia/Shanghai",
                override_now=state.get("override_now"),
                settings_fixed_now=getattr(self.settings, "fixed_now", None),
            )
            time_payload = datetime_payload_from_time_context(ctx)
            state["time_context_result"] = time_payload
            state["time_context_payload"] = {"timezone": ctx.timezone, "override_now": state.get("override_now")}
            state["runtime_context"] = {
                "user_id": state.get("user_id"),
                "role": role,
                "permissions": state["permissions"],
                "allowed_kbs": allowed_kbs,
                "requested_kbs": state.get("requested_kbs") or [],
                "time_context_result": time_payload,
                "capability_catalog": state["capability_catalog"],
                "session_id": state.get("session_id"),
                "workflow_run_id": state.get("workflow_run_id"),
                "question": state.get("question"),
                "user_context": {"user_id": state.get("user_id"), "role": role},
            }
            state.setdefault("observations", []).append(
                {"type": "runtime_context", "role": role, "current_date": time_payload.get("current_date"), "allowed_kbs": allowed_kbs}
            )
            summary, details = summarize_runtime_context(state)
            append_mainline_step(state, stage="runtime_context", title="构建运行上下文", summary=summary, details=details)
            refresh_state_views(state)
        return state

    def plan_with_llm(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "plan_with_llm"):
            if state.get("error") and state.get("route") == "reject":
                state["raw_plan"] = {"overall_intent": "reject", "tasks": [], "answer_style": "concise"}
                state["execution_plan"] = {"tasks": [], "strategy": "blocked"}
                state["planner_schema_version"] = "runtime_v2"
                refresh_state_views(state)
                return state
            question = str(state.get("question") or "")
            default = {
                "overall_intent": "rag",
                "requires_tools": False,
                "requires_rag": True,
                "tasks": [{"task_id": "t1", "kind": "rag", "objective": question, "rag_query": question}],
                "answer_style": "concise",
            }
            payload = self._invoke_json(
                state=state,
                node="plan_with_llm",
                system=PLAN_WITH_LLM_SYSTEM,
                user=format_plan_with_llm_user(
                    question=question,
                    role=normalize_role(state.get("role")),
                    planning_context=state.get("planning_context") or {},
                    capability_catalog=str(state.get("available_tool_contracts") or "[]"),
                    permissions=state.get("permissions") or {},
                    time_context=state.get("time_context_result") or {},
                ),
                default=default,
            )
            normalized = self._normalize_runtime_plan(payload if isinstance(payload, dict) else default, question)
            state["raw_plan"] = normalized
            state["planner_schema_version"] = "runtime_v2"
            self._apply_runtime_plan_to_state(state, normalized)
            state.setdefault("observations", []).append(
                {"type": "plan_with_llm", "overall_intent": normalized.get("overall_intent"), "task_count": len(normalized["tasks"])}
            )
            summary, details = summarize_plan(state)
            append_mainline_step(state, stage="plan_with_llm", title="生成执行计划", summary=summary, details=details)
            refresh_state_views(state)
        return state

    def resolve_plan_time(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "resolve_plan_time"):
            time_context = state.get("time_context_result") or {}
            if not time_context.get("current_date"):
                ctx = build_time_context(timezone="Asia/Shanghai", override_now=state.get("override_now"), settings_fixed_now=getattr(self.settings, "fixed_now", None))
                time_context = datetime_payload_from_time_context(ctx)
                state["time_context_result"] = time_context
            plan = dict(state.get("execution_plan") or {})
            expanded_tasks: list[dict[str, Any]] = []
            facts: list[dict[str, Any]] = []
            for task in [dict(item) for item in plan.get("tasks") or [] if isinstance(item, dict)]:
                expression = str(task.get("time_expression") or "").strip()
                if not expression:
                    expanded_tasks.append(task)
                    continue
                resolved = resolve_time_expression(
                    expression,
                    time_context,
                    reference_text=" ".join(
                        str(value or "")
                        for value in (
                            task.get("objective"),
                            task.get("query"),
                            task.get("rag_query"),
                            task.get("action"),
                            (task.get("tool_input") or {}).get("action") if isinstance(task.get("tool_input"), dict) else "",
                            (task.get("tool_input") or {}).get("time") if isinstance(task.get("tool_input"), dict) else "",
                        )
                    ),
                )
                task["resolved_time"] = resolved
                facts.append({"task_id": task.get("task_id"), "time_expression": expression, "kind": resolved.get("kind"), "items": resolved.get("items") or [], "resolved_time": resolved})
                expanded_tasks.extend(self._expand_task_by_resolved_time(task))
            plan["tasks"] = expanded_tasks
            state["execution_plan"] = plan
            state["task_queue"] = list(expanded_tasks)
            state["resolved_time_facts"] = facts
            state.setdefault("observations", []).append({"type": "time_resolution", "facts": facts})
            summary, details = summarize_time_resolution(state)
            append_mainline_step(state, stage="resolve_plan_time", title="解析时间信息", summary=summary, details=details)
            refresh_state_views(state)
        return state

    def validate_plan(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "validate_plan"):
            if state.get("error") and state.get("route") == "reject":
                state["plan_validation"] = {"validation_status": "refused", "validation_issues": [state.get("error")]}
                refresh_state_views(state)
                return state
            if self._is_dangerous_question(state.get("question", ""), state.get("standalone_query", "")):
                state.update({"route": "reject", "intent": "reject", "risk_level": "high", "final_answer": "抱歉，这个请求存在安全风险，我不能执行。"})
                state["plan_validation"] = {"validation_status": "refused", "validation_issues": ["unsafe request"]}
                refresh_state_views(state)
                return state

            role = normalize_role(state.get("role"))
            role_policies = self._get_role_policies(state)
            tasks = [dict(item) for item in (state.get("execution_plan") or {}).get("tasks") or [] if isinstance(item, dict)]
            if self._calendar_write_requires_explicit_target_clarification(state, tasks):
                return self._block_plan(state, "ambiguous calendar target without prior context", intent="need_clarification")

            executable_tasks: list[dict[str, Any]] = []
            blocked_tasks: list[dict[str, Any]] = []
            clarification_tasks: list[dict[str, Any]] = []
            validation_issues: list[dict[str, Any]] = []

            for task in tasks:
                if task.get("kind") != "tool":
                    executable_tasks.append(task)
                    continue
                tool = str(task.get("tool") or task.get("tool_name") or "")
                action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "*").lower() or "*"
                if not self.tool_registry.has_tool(tool):
                    issue = {"task_id": task.get("task_id"), "layer": "validator", "code": "unknown_tool", "message": f"unknown tool {tool}"}
                    validation_issues.append(issue)
                    blocked_tasks.append({**task, "_validation_issue": issue})
                    continue
                allowed = self.tool_registry.allowed_actions(tool, role, role_policies=role_policies)
                if "*" not in allowed and action not in allowed:
                    issue = {
                        "task_id": task.get("task_id"),
                        "layer": "validator",
                        "code": "permission_denied",
                        "message": f"{role} cannot {tool}.{action}",
                    }
                    validation_issues.append(issue)
                    blocked_tasks.append({**task, "_validation_issue": issue})
                    state.setdefault("audit_events", []).append(
                        {
                            "event": "permission_blocked_task",
                            "decision": "blocked",
                            "tool": tool,
                            "action": action,
                            "role": role,
                            "message": friendly_permission_answer(role, tool, action),
                            "task_id": task.get("task_id"),
                        }
                    )
                    continue
                for field in ("date", "start_date", "end_date"):
                    value = str((task.get("tool_input") or {}).get(field) or "").strip()
                    if value and not self._is_iso_date(value):
                        issue = {
                            "task_id": task.get("task_id"),
                            "layer": "validator",
                            "code": "unresolved_date",
                            "field": field,
                            "message": f"unresolved date field {field}",
                        }
                        validation_issues.append(issue)
                        clarification_tasks.append({**task, "_validation_issue": issue})
                        break
                else:
                    candidate_tasks = executable_tasks + [task]
                    payload = {
                        "route": state.get("route"),
                        "intent": state.get("intent"),
                        "standalone_query": state.get("standalone_query"),
                        "execution_plan": {"tasks": candidate_tasks, "strategy": (state.get("execution_plan") or {}).get("strategy", "")},
                        "selected_tool": state.get("selected_tool"),
                        "selected_action": state.get("selected_action"),
                        "tool_input": state.get("tool_input"),
                    }
                    gated = apply_capability_gates(payload, candidate_tasks, role=role, tool_registry=self.tool_registry, role_policies=role_policies, state=state)
                    if gated is not None:
                        issues = gated.get("validation_issues") or [
                            {
                                "task_id": task.get("task_id"),
                                "layer": "validator",
                                "code": gated.get("topic") or "capability_gate",
                                "message": gated.get("normalization_reason") or "capability validation failed",
                            }
                        ]
                        issue = dict(issues[0]) if isinstance(issues[0], dict) else {"task_id": task.get("task_id"), "message": str(issues[0])}
                        issue.setdefault("task_id", task.get("task_id"))
                        validation_issues.extend([dict(item) if isinstance(item, dict) else {"task_id": task.get("task_id"), "message": str(item)} for item in issues])
                        if gated.get("intent") == "permission_required" or gated.get("validation_status") == "refused":
                            blocked_tasks.append({**task, "_validation_issue": issue})
                        else:
                            clarification_tasks.append({**task, "_validation_issue": issue})
                        continue
                    executable_tasks.append(task)

            if not tasks and not blocked_tasks and not clarification_tasks:
                state["execution_plan"] = {"tasks": [], "strategy": (state.get("execution_plan") or {}).get("strategy", "")}
                state["task_queue"] = []
                state["current_task"] = {}
                state["selected_tool"] = None
                state["selected_action"] = None
                state["tool_input"] = {}
                state["required_tools"] = []
                state["route"] = "direct"
                state["plan_validation"] = {
                    "validation_status": "valid",
                    "validation_issues": [],
                    "executable_tasks": [],
                    "blocked_tasks": [],
                    "clarification_tasks": [],
                }
            elif executable_tasks:
                state["execution_plan"] = {"tasks": executable_tasks, "strategy": (state.get("execution_plan") or {}).get("strategy", "")}
                self._prime_first_task_fields(state, executable_tasks)
                state["task_queue"] = list(executable_tasks)
                status = "partial" if blocked_tasks or clarification_tasks else "valid"
                state["plan_validation"] = {
                    "validation_status": status,
                    "validation_issues": validation_issues,
                    "executable_tasks": executable_tasks,
                    "blocked_tasks": blocked_tasks,
                    "clarification_tasks": clarification_tasks,
                }
            else:
                intent = "permission_required" if blocked_tasks and not clarification_tasks else "need_clarification"
                state.update(
                    {
                        "route": "direct",
                        "intent": intent,
                        "selected_tool": None,
                        "selected_action": None,
                        "tool_input": {},
                        "required_tools": [],
                        "execution_plan": {"tasks": [], "strategy": (state.get("execution_plan") or {}).get("strategy", "")},
                    }
                )
                state["task_queue"] = []
                state["plan_validation"] = {
                    "validation_status": "refused" if intent == "permission_required" else "needs_clarification",
                    "validation_issues": validation_issues,
                    "executable_tasks": [],
                    "blocked_tasks": blocked_tasks,
                    "clarification_tasks": clarification_tasks,
                }
                state["final_answer"] = "你没有权限，也无权执行该操作。" if intent == "permission_required" else "需要补充或澄清信息后才能执行。"
            state.setdefault("observations", []).append({"type": "plan_validation", **state["plan_validation"]})
            summary, details = summarize_validation(state)
            append_mainline_step(state, stage="validate_plan", title="校验执行计划", summary=summary, details=details)
            refresh_state_views(state)
        return state

    def react_execute(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "react_execute"):
            state["task_queue"] = [dict(task) for task in (state.get("execution_plan") or {}).get("tasks") or [] if isinstance(task, dict)]
            executor = ReActExecutor(max_steps=5)

            def next_action(current_state: dict[str, Any], step: int, remaining: list[dict[str, Any]]) -> dict[str, Any]:
                default = {"next_action": "finish", "finish_reason": "all facts are available"}
                payload = self._invoke_json(
                    state=current_state,  # type: ignore[arg-type]
                    node="react_execute.next_action",
                    system=REACT_NEXT_ACTION_SYSTEM,
                    user=format_react_next_action_user(
                        question=str(current_state.get("question") or ""),
                        plan=current_state.get("execution_plan") or {},
                        remaining_tasks=remaining,
                        completed_tasks=[str(x) for x in current_state.get("completed_tasks") or []],
                        observations=current_state.get("observations") or [],
                        resolved_time_facts=current_state.get("resolved_time_facts") or [],
                    ),
                    default=default,
                )
                return payload if isinstance(payload, dict) else default

            try:
                result = executor.run(state, next_action=next_action, call_tool=self._make_tool_callback(state), search_rag=self._make_rag_callback(state))
            except ReActGuardrailViolation as exc:
                step = {
                    "step": len(state.get("react_steps") or []) + 1,
                    "action": "guardrail_violation",
                    "status": "blocked",
                    "summary": str(exc),
                    "facts": [],
                }
                state.setdefault("observations", []).append({"type": "react_observation", **step})
                result = ReActExecutionResult(status="blocked", steps=(step,), finish_reason=str(exc))
            state["react_status"] = result.status
            state["react_steps"] = list(result.steps)
            state.setdefault("completion_assessment", {}).update(
                {
                    "ready_to_answer": result.status in {"success", "partial"},
                    "reason": result.finish_reason,
                    "execution_status": result.status,
                }
            )
            summary, details = summarize_react_execution(state)
            append_mainline_step(state, stage="react_execute", title="执行任务", summary=summary, details=details)
            refresh_state_views(state)
        return state

    def answer_with_llm(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "answer_with_llm"):
            result = self.answer_service.generate(state)
            summary, details = summarize_answer(result)
            append_mainline_step(result, stage="answer_with_llm", title="生成最终回答", summary=summary, details=details)
            refresh_state_views(result)
            return result

    def stream_generate_answer(self, state: AgentState):
        with NodeTimer(state, "answer_with_llm"):
            yield from self.answer_service.stream(state)

    def update_memory(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "update_memory"):
            service = MemoryService(
                context_store=self.context_store,
                invoke_json=self._invoke_json,
                build_trace=self.build_trace,
                should_use_lightweight_memory=self._should_use_lightweight_memory,
                on_complete=lambda s: self._role_policy_snapshots.pop(str(s.get("workflow_run_id") or s.get("trace_id") or id(s)), None),
            )
            result = service.update_memory(state)
            summary, details = summarize_memory(result)
            append_mainline_step(result, stage="update_memory", title="更新记忆", summary=summary, details=details)
            refresh_state_views(result)
            return result

    def _call_tool(self, state: AgentState) -> AgentState:
        return execute_selected_tool(
            state,
            tool_registry=self.tool_registry,
            role_policies=self._get_role_policies(state),
            build_payload=self._build_tool_payload,
            verify_tool_result=self._verify_tool_result_consistency,
            build_current_tool_context=self._build_current_tool_context,
            record_tool_task_result=self._record_tool_task_result,
            friendly_tool_error=self._friendly_tool_error,
            friendly_tool_validation_error=self._friendly_tool_validation_error,
            friendly_permission_answer=self._friendly_permission_answer,
        )

    def build_trace(self, state: AgentState) -> dict[str, Any]:
        return self.trace_builder.build_trace(state)

    # ReAct callbacks are closures so the executor receives stateful operations.
    def _make_tool_callback(self, state: AgentState):
        def call_tool_task(task: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
            executable = dict(task)
            action_input = action.get("tool_input") if isinstance(action.get("tool_input"), dict) else {}
            if action_input:
                merged = dict(executable.get("tool_input") or {})
                for key, value in action_input.items():
                    merged.setdefault(key, value)
                executable["tool_input"] = merged
            if (
                str(executable.get("tool") or executable.get("tool_name") or "") == "manage_company_calendar"
                and str(executable.get("action") or (executable.get("tool_input") or {}).get("action") or "").lower() in {"update", "delete"}
            ):
                before_resolution = len(state.get("task_results") or [])
                resolved_task = self.calendar_task_resolver.resolve_task_from_context(state, executable)
                self._sync_execution_plan_from_queue(state)
                if resolved_task is None:
                    latest = self._latest_task_result(state, before_resolution)
                    status = str(latest.get("status") or "need_clarification")
                    return {
                        "status": status,
                        "summary": str(latest.get("result_summary") or "需要补充或澄清信息后才能执行。"),
                        "raw_result": latest.get("tool_result") if isinstance(latest.get("tool_result"), dict) else {},
                        "facts": latest.get("facts") or [],
                    }
                executable = resolved_task
            state["current_task"] = executable
            self._apply_execution_task_to_state(state, executable)
            before = len(state.get("task_results") or [])
            self._call_tool(state)
            latest = self._latest_task_result(state, before)
            if latest.get("tool_name") == "manage_company_calendar" and latest.get("action") == "query" and latest.get("status") in {"ok", "success"}:
                if self.calendar_task_resolver.resolve_updates(state) or self.calendar_task_resolver.resolve_deletes(state):
                    self._sync_execution_plan_from_queue(state)
            status = str(latest.get("status") or ("error" if state.get("error") else "success"))
            return {
                "status": "success" if status in {"ok", "success"} else status,
                "summary": str(latest.get("result_summary") or state.get("final_answer") or ""),
                "raw_result": latest.get("tool_result") if isinstance(latest.get("tool_result"), dict) else state.get("tool_result") or {},
                "facts": latest.get("facts") or [],
            }

        return call_tool_task

    def _make_rag_callback(self, state: AgentState):
        def search_rag_task(task: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
            executable = dict(task)
            query = str(action.get("rag_query") or executable.get("rag_query") or executable.get("query") or executable.get("objective") or "").strip()
            executable["query"] = query
            state["current_task"] = executable
            state["pending_search_tasks"] = [{"task_id": executable.get("task_id"), "objective": executable.get("objective") or query, "query": query, "top_k": self.settings.top_k, "candidate_k": self.settings.candidate_k}]
            before = len(state.get("task_results") or [])
            try:
                self.rag_service.retrieve(state)
            except PermissionError as exc:
                return {"status": "blocked", "summary": str(exc), "raw_result": {"error": "permission denied"}, "facts": []}
            latest = self._latest_task_result(state, before)
            return {
                "status": "success" if str(latest.get("status") or "") == "ok" else str(latest.get("status") or "empty"),
                "summary": str(latest.get("evidence_summary") or latest.get("unsupported_reason") or ""),
                "raw_result": {"sources": latest.get("sources") or [], "candidate_sources": latest.get("candidate_sources") or []},
                "facts": latest.get("sources") or [],
            }

        return search_rag_task

    # ---------- normalization and execution helpers ----------
    @staticmethod
    def _normalize_runtime_plan(payload: dict[str, Any], question: str) -> dict[str, Any]:
        raw_tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else []
        overall_raw = str(payload.get("overall_intent") or payload.get("route") or "").strip().lower()
        knowledge_requirement = payload.get("knowledge_requirement") if isinstance(payload.get("knowledge_requirement"), dict) else {}
        requires_rag = bool(payload.get("requires_rag") or knowledge_requirement.get("should_use_rag") or overall_raw == "rag")
        requires_tools = bool(payload.get("requires_tools"))
        tasks: list[dict[str, Any]] = []
        for idx, raw_task in enumerate(raw_tasks, start=1):
            if not isinstance(raw_task, dict):
                continue
            kind = str(raw_task.get("kind") or "").strip().lower()
            tool = str(raw_task.get("tool_name") or raw_task.get("tool") or "").strip() or None
            if not kind:
                kind = "tool" if tool else "rag" if raw_task.get("rag_query") or raw_task.get("query") else "answer"
            if kind == "direct":
                kind = "answer"
            if kind not in {"tool", "rag", "answer"}:
                continue
            tool_input = raw_task.get("tool_input") if isinstance(raw_task.get("tool_input"), dict) else {}
            action = str(raw_task.get("action") or tool_input.get("action") or "").strip() or None
            task = {
                "task_id": str(raw_task.get("task_id") or raw_task.get("id") or f"t{idx}"),
                "kind": kind,
                "objective": str(raw_task.get("objective") or raw_task.get("query") or raw_task.get("rag_query") or question).strip(),
                "tool": tool,
                "tool_name": tool,
                "action": action,
                "time_expression": str(raw_task.get("time_expression") or "").strip(),
                "tool_input": dict(tool_input),
                "query": str(raw_task.get("rag_query") or raw_task.get("query") or raw_task.get("objective") or "").strip(),
                "rag_query": str(raw_task.get("rag_query") or raw_task.get("query") or "").strip() or None,
                "depends_on": [str(item) for item in coerce_list(raw_task.get("depends_on"))],
            }
            if kind == "tool" and tool == "manage_company_calendar" and action and not task["tool_input"].get("action"):
                task["tool_input"]["action"] = action
            if kind == "tool" and tool == "query_attendance_summary":
                task["action"] = "query" if action in {None, "", "*"} else action
            if kind == "rag" and not task["query"]:
                task["query"] = question
                task["rag_query"] = question
            tasks.append({key: value for key, value in task.items() if value not in (None, "", [], {}) or key in {"task_id", "kind", "tool_input"}})
        if not tasks:
            if requires_rag or overall_raw in {"rag", "mixed"}:
                tasks = [{"task_id": "t1", "kind": "rag", "objective": question, "query": question, "rag_query": question, "tool_input": {}}]
            elif overall_raw in {"smalltalk", "direct", "datetime"} and not requires_tools:
                tasks = []
        has_tool = any(task.get("kind") == "tool" for task in tasks)
        has_rag = any(task.get("kind") == "rag" for task in tasks)
        overall = str(payload.get("overall_intent") or ("mixed" if has_tool and has_rag else "calendar" if has_tool else "rag" if has_rag else "direct"))
        return {"overall_intent": overall, "requires_tools": has_tool, "requires_rag": has_rag, "tasks": tasks, "execution_plan": {"tasks": tasks, "strategy": str(payload.get("answer_style") or "concise")}, "answer_style": str(payload.get("answer_style") or "concise")}

    def _apply_runtime_plan_to_state(self, state: AgentState, payload: dict[str, Any]) -> None:
        tasks = list((payload.get("execution_plan") or {}).get("tasks") or [])
        has_tool = any(isinstance(task, dict) and task.get("kind") == "tool" for task in tasks)
        has_rag = any(isinstance(task, dict) and task.get("kind") == "rag" for task in tasks)
        state["intent"] = str(payload.get("overall_intent") or ("mixed" if has_tool and has_rag else "daily_tool" if has_tool else "rag_fact" if has_rag else "direct"))
        state["route"] = "rag" if has_rag else "tool" if has_tool else "direct"  # type: ignore[assignment]
        state["standalone_query"] = str(state.get("question") or "")
        state["execution_plan"] = {"tasks": tasks, "strategy": str(payload.get("answer_style") or "concise")}
        state["task_queue"] = list(tasks)
        self._prime_first_task_fields(state, tasks)
        state["knowledge_requirement"] = {"requires_company_knowledge": has_rag or has_tool, "should_use_rag": has_rag}

    def _prime_first_task_fields(self, state: AgentState, tasks: list[dict[str, Any]]) -> None:
        first_tool = next((task for task in tasks if isinstance(task, dict) and task.get("kind") == "tool"), {})
        state["current_task"] = dict(tasks[0]) if tasks else {}
        state["selected_tool"] = str(first_tool.get("tool") or first_tool.get("tool_name") or "") or None
        state["selected_action"] = str(first_tool.get("action") or (first_tool.get("tool_input") or {}).get("action") or "") or None
        state["required_tools"] = [state["selected_tool"]] if state.get("selected_tool") else []
        state["tool_input"] = dict(first_tool.get("tool_input") or {}) if first_tool else {}

    @staticmethod
    def _apply_resolved_time_to_task(task: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        output = dict(task)
        output["resolved_time"] = {"kind": "range" if item.get("start_date") != item.get("end_date") else "date", "items": [dict(item)]}
        tool = str(output.get("tool") or output.get("tool_name") or "")
        action = str(output.get("action") or (output.get("tool_input") or {}).get("action") or "query").lower()
        tool_input = dict(output.get("tool_input") or {})
        start = str(item.get("start_date") or "")
        end = str(item.get("end_date") or start)
        if tool in {"manage_company_calendar", "query_attendance_summary"} and action in {"query", "*"}:
            tool_input.pop("date", None)
            tool_input["start_date"] = start
            tool_input["end_date"] = end
            if tool == "manage_company_calendar":
                tool_input.setdefault("query_scope", "all_events" if str(tool_input.get("event_type") or "all") == "all" else "type_filtered")
                tool_input.setdefault("department", "all")
        elif tool == "manage_company_calendar" and action in {"create", "update"}:
            if action == "create" or start == end:
                tool_input["date"] = start
        output["tool_input"] = tool_input
        return output

    def _expand_task_by_resolved_time(self, task: dict[str, Any]) -> list[dict[str, Any]]:
        resolved = task.get("resolved_time") if isinstance(task.get("resolved_time"), dict) else {}
        items = [dict(item) for item in (resolved.get("items") or []) if isinstance(item, dict)]
        if not items:
            return [task]
        tool = str(task.get("tool") or task.get("tool_name") or "")
        action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower()
        if resolved.get("kind") == "multi" and task.get("kind") == "tool" and action == "query" and tool in {"manage_company_calendar", "query_attendance_summary"}:
            split_tasks: list[dict[str, Any]] = []
            for idx, item in enumerate(items, start=1):
                split = self._apply_resolved_time_to_task(task, item)
                split["task_id"] = f"{task.get('task_id')}_{idx}"
                split["time_expression"] = item.get("label") or task.get("time_expression")
                split["objective"] = f"{task.get('objective') or ''}（{split['time_expression']}）".strip()
                split_tasks.append(split)
            return split_tasks
        return [self._apply_resolved_time_to_task(task, items[0])]

    def _apply_execution_task_to_state(self, state: AgentState, task: dict[str, Any]) -> None:
        if str(task.get("kind") or "") == "tool":
            tool_name = str(task.get("tool") or task.get("tool_name") or "").strip()
            action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").strip() or None
            state["route"] = "tool"
            state["selected_tool"] = tool_name or None
            state["selected_action"] = action
            state["required_tools"] = [tool_name] if tool_name else []
            state["tool_input"] = dict(task.get("tool_input") or {})

    def _record_tool_task_result(self, state: AgentState, before_tool_calls: int = 0) -> None:
        task = state.get("current_task") if isinstance(state.get("current_task"), dict) else {}
        if str(task.get("kind") or "") != "tool":
            return
        task_id = str(task.get("task_id") or "")
        if not task_id:
            return
        result = dict(state.get("tool_result") or {})
        tool_name = str(state.get("selected_tool") or task.get("tool") or task.get("tool_name") or "")
        action = str(state.get("selected_action") or task.get("action") or (state.get("tool_input") or {}).get("action") or "*")
        status = "error" if result.get("error") or state.get("error") else "ok"
        state.setdefault("task_results", []).append(
            {
                "task_id": task_id,
                "kind": "tool",
                "objective": task.get("objective") or tool_name,
                "status": status,
                "tool_name": tool_name,
                "action": action,
                "tool_input": {key: value for key, value in (state.get("tool_input") or {}).items() if key not in {"query", "user_id", "role"}},
                "tool_result": result,
                "tool_calls": list(state.get("tool_calls") or [])[max(0, before_tool_calls):],
                "result_summary": format_tool_result(tool_name, result, context=str(task.get("objective") or state.get("question") or "")) if result else "",
                "error_message": state.get("final_answer") if status == "error" else "",
            }
        )
        if status == "ok" and task_id not in set(state.get("completed_tasks") or []):
            state.setdefault("completed_tasks", []).append(task_id)

    @staticmethod
    def _latest_task_result(state: AgentState, before: int) -> dict[str, Any]:
        return next((item for item in reversed((state.get("task_results") or [])[before:]) if isinstance(item, dict)), {})

    def _block_plan(self, state: AgentState, reason: str, *, intent: str) -> AgentState:
        state.update({"route": "direct", "intent": intent, "selected_tool": None, "selected_action": None, "execution_plan": {"tasks": [], "strategy": ""}, "plan_validation": {"validation_status": "refused" if intent == "permission_required" else "needs_clarification", "validation_issues": [reason]}})
        if intent == "permission_required":
            state["final_answer"] = "你没有权限，也无权执行该操作。"
        elif "calendar target" in reason:
            state["final_answer"] = "请说明具体要修改哪一个公司日程，例如提供 event_id、会议标题和日期，或先查询后指定第几个；在目标明确前我不会执行修改或删除。"
        else:
            state["final_answer"] = "需要补充或澄清信息后才能执行。"
        refresh_state_views(state)
        return state

    def _calendar_write_requires_explicit_target_clarification(self, state: AgentState, tasks: list[dict[str, Any]]) -> bool:
        text = str(state.get("question") or state.get("standalone_query") or "")
        asks_for_read_answer = any(token in text for token in ("查询", "查一下", "查看", "告诉我", "安排"))
        asks_about_ability = any(token in text for token in ("能不能", "能否", "是否可以", "可不可以", "可以吗"))
        if asks_for_read_answer and asks_about_ability:
            return False
        if not any(token in text for token in ("那个", "这个", "它", "该会议", "该日程", "那场", "这场")):
            return False
        previous = state.get("previous_tool_context") if isinstance(state.get("previous_tool_context"), dict) else {}
        has_dependency_query = any(
            isinstance(task, dict)
            and str(task.get("kind") or "") == "tool"
            and str(task.get("tool") or task.get("tool_name") or "") == "manage_company_calendar"
            and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() == "query"
            for task in tasks
        )
        if (previous.get("events") or previous.get("event")) and not has_dependency_query:
            return False
        if any(token in text for token in ("第一个", "第一条", "第二个", "第二条", "所有", "全部")):
            return False
        for task in tasks:
            if not isinstance(task, dict) or str(task.get("kind") or "") != "tool":
                continue
            if str(task.get("tool") or task.get("tool_name") or "") != "manage_company_calendar":
                continue
            action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower()
            if action not in {"update", "delete"}:
                continue
            tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else {}
            if is_unresolved_calendar_event_id(tool_input.get("event_id")):
                return True
        return False

    def _preserve_read_tasks_for_denied_write(
        self,
        state: AgentState,
        tasks: list[dict[str, Any]],
        denied_task: dict[str, Any],
    ) -> bool:
        action = str(denied_task.get("action") or (denied_task.get("tool_input") or {}).get("action") or "").lower()
        if action not in {"create", "update", "delete"}:
            return False
        text = str(state.get("question") or state.get("standalone_query") or "")
        asks_for_read_answer = any(token in text for token in ("查询", "查一下", "查看", "告诉我", "安排"))
        asks_about_ability = any(token in text for token in ("能不能", "能否", "是否可以", "可不可以", "可以吗"))
        if not (asks_for_read_answer and asks_about_ability):
            return False
        return any(
            isinstance(task, dict)
            and task is not denied_task
            and str(task.get("kind") or "").lower() == "tool"
            and str(task.get("action") or (task.get("tool_input") or {}).get("action") or "").lower() == "query"
            for task in tasks
        )

    def _drop_disallowed_write_tasks(self, state: AgentState, tasks: list[dict[str, Any]], role: str, role_policies: Any) -> None:
        allowed_tasks: list[dict[str, Any]] = []
        denied_events: list[dict[str, Any]] = []
        for task in tasks:
            tool = str(task.get("tool") or task.get("tool_name") or "")
            action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "*").lower() or "*"
            if str(task.get("kind") or "") == "tool":
                allowed = self.tool_registry.allowed_actions(tool, role, role_policies=role_policies)
                if "*" not in allowed and action not in allowed:
                    denied_events.append(
                        {
                            "event": "permission_blocked_task",
                            "decision": "blocked",
                            "tool": tool,
                            "action": action,
                            "role": role,
                            "message": friendly_permission_answer(role, tool, action),
                        }
                    )
                    continue
            allowed_tasks.append(task)
        state.setdefault("audit_events", []).extend(denied_events)
        state.setdefault("observations", []).extend(
            {"type": "permission_event", "status": "blocked", **event} for event in denied_events
        )
        if denied_events:
            state["final_answer"] = denied_events[0]["message"]
        state["execution_plan"] = {"tasks": allowed_tasks, "strategy": (state.get("execution_plan") or {}).get("strategy", "")}
        state["task_queue"] = list(allowed_tasks)
        self._prime_first_task_fields(state, allowed_tasks)

    def _sync_execution_plan_from_queue(self, state: AgentState) -> None:
        queue = [dict(task) for task in (state.get("task_queue") or []) if isinstance(task, dict)]
        if not queue:
            return
        plan = dict(state.get("execution_plan") or {})
        plan["tasks"] = queue
        state["execution_plan"] = plan

    @staticmethod
    def _is_iso_date(value: str) -> bool:
        try:
            from datetime import date

            date.fromisoformat(value)
            return True
        except Exception:
            return False

    # ---------- tool/runtime helpers ----------
    def _build_tool_payload(self, state: AgentState, tool_name: str, role: str) -> dict[str, Any]:
        return build_tool_payload(state, tool_name, role, run_datetime_for_tool=self._run_datetime_for_tool, finalize_tool_input=lambda _s, _t, payload, _d, _e: payload)

    def _run_datetime_for_tool(self, state: AgentState, role: str) -> dict[str, Any]:
        assert_tool_action_permission(role, "get_current_datetime", "*", role_policies=self._get_role_policies(state))
        cached = state.get("time_context_result")
        if isinstance(cached, dict) and cached.get("current_date"):
            return cached
        payload = default_datetime_payload()
        if state.get("override_now"):
            payload["override_now"] = state.get("override_now")
        result = self._datetime_tool_callable()(payload)
        state["time_context_payload"] = dict(payload)
        state["time_context_result"] = dict(result)
        state.setdefault("tool_calls", []).append({"tool_name": "get_current_datetime", "action": "*", "args": payload, "ok": not bool(result.get("error")), "purpose": "resolve_time_reference"})
        return result

    @staticmethod
    def _datetime_tool_callable() -> Any:
        return get_current_datetime

    @staticmethod
    def _verify_tool_result_consistency(tool_name: str, payload: dict[str, Any], result: dict[str, Any]) -> None:
        verify_domain_tool_result(tool_name, payload, result)

    @staticmethod
    def _friendly_tool_error(tool_name: str, result: dict[str, Any], role: str | None = None, action: str | None = None) -> str:
        return friendly_tool_error(tool_name, result, role=role, action=action)

    @staticmethod
    def _friendly_tool_validation_error(tool_name: str, exc: ValidationError) -> str:
        return friendly_tool_validation_error(tool_name, exc)

    @staticmethod
    def _friendly_permission_answer(role: str, tool_name: str, action: str | None = None) -> str:
        return friendly_permission_answer(role, tool_name, action)

    @staticmethod
    def _build_current_tool_context(tool_name: str, payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        return build_tool_context(tool_name, payload, result)

    def _role_allowed_actions_for_answer(self, state: dict[str, Any]) -> dict[str, list[str]]:
        role = normalize_role(state.get("role"))
        role_policies = self._get_role_policies(state)  # type: ignore[arg-type]
        actions: dict[str, list[str]] = {}
        for tool in self.tool_registry.list_tools():
            name = str(tool.get("name") or "")
            allowed = self.tool_registry.allowed_actions(name, role, role_policies=role_policies)
            if allowed:
                actions[name] = sorted(allowed)
        return actions

    def _get_retriever(self) -> Any:
        if self.retriever is None:
            from mini_rag.retrieval.retriever import KnowledgeBaseRetriever

            self.retriever = KnowledgeBaseRetriever(self.settings)
        return self.retriever

    def _get_role_policies(self, state: AgentState) -> Any:
        key = str(state.get("workflow_run_id") or state.get("trace_id") or id(state))
        cached = self._role_policy_snapshots.get(key)
        if cached is not None:
            return cached
        policies = self.auth_store.list_role_policies()
        if len(self._role_policy_snapshots) > 128:
            self._role_policy_snapshots.pop(next(iter(self._role_policy_snapshots)), None)
        self._role_policy_snapshots[key] = policies
        return policies

    def _append_llm_call_trace(self, state: AgentState, *, node: str, model: str, system: str, user: str, output: str, latency_ms: float, streaming: bool = False) -> dict[str, Any]:
        return self.trace_builder.append_llm_call_trace(state, node=node, model=model, system=system, user=user, output=output, latency_ms=latency_ms, streaming=streaming)

    def _invoke_text(self, state: AgentState, node: str, system: str, user: str, llm: Any | None = None, model_name: str | None = None) -> str:
        model = model_name or self.settings.qwen_control_model or self.settings.qwen_chat_model
        start = time.perf_counter()
        message = (llm or self.control_llm).invoke([("system", system), ("user", user)])
        content = get_message_content(message)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        self._append_llm_call_trace(state, node=node, model=model, system=system, user=user, output=content, latency_ms=elapsed_ms)
        return content

    def _invoke_json(self, state: AgentState, node: str, system: str, user: str, default: dict[str, Any]) -> dict[str, Any]:
        before = len(state.get("llm_calls") or [])
        raw = self._invoke_text(state=state, node=node, system=system, user=user, llm=self.control_llm)
        parsed = safe_json_loads(raw, default=None)
        payload = parsed if isinstance(parsed, dict) else default
        calls = state.get("llm_calls") or []
        if len(calls) > before:
            calls[-1]["json_parse_ok"] = isinstance(parsed, dict)
            if bool(getattr(self.settings, "trace_llm_io", True)):
                calls[-1]["parsed_output"] = payload
        return payload

    @staticmethod
    def _is_dangerous_question(question: str, standalone_query: str) -> bool:
        text = f"{question} {standalone_query}".lower()
        return any(term in text for term in ("api key", "apikey", "secret", "密钥", "泄露", "密码", "token"))

    @staticmethod
    def _should_use_lightweight_memory(state: AgentState) -> bool:
        return len(str(state.get("final_answer") or "")) <= 1600


__all__ = ["AgenticRAGNodes", "create_initial_state", "get_current_datetime", "GENERATE_ANSWER_SYSTEM"]
