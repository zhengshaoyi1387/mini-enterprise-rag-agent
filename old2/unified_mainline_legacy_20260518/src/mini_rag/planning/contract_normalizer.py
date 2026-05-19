from __future__ import annotations

from typing import Any

from mini_rag.capabilities.calendar.compiler import maybe_add_calendar_query_task, maybe_add_query_first_update_task
from mini_rag.capabilities.calendar.validator import (
    calendar_write_needs_clarification as calendar_write_target_needs_clarification,
    has_executable_calendar_query_source as calendar_has_executable_query_source,
)
from mini_rag.capabilities.datetime.resolver import (
    repair_execution_plan_time_contract,
    time_requirement_from_payload,
)
from mini_rag.planning.compiler import PlanCompiler
from mini_rag.planning.gates import apply_capability_gates, first_disallowed_tool_task


class PlanningContractNormalizer:
    """Normalize planner JSON into an executable, permission-aware contract.

    This class owns the boundary between fuzzy LLM planner output and the graph
    executor. The graph node should not contain tool-specific repair branches.
    """

    def __init__(self, tool_registry: Any) -> None:
        self.tool_registry = tool_registry
        self.compiler = PlanCompiler()

    def normalize_knowledge_requirement(self, value: Any) -> dict[str, Any]:
        return self.compiler.normalize_knowledge_requirement(value)

    def execution_plan_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.compiler.execution_plan_from_payload(payload)

    def normalize_execution_task(self, task: Any, idx: int) -> dict[str, Any]:
        return self.compiler.normalize_execution_task(task, idx)

    def normalize_classification_payload(self, payload: dict[str, Any], question: str) -> dict[str, Any]:
        return self.compiler.normalize_classification_payload(payload, question)

    def default_plan_from_classification(self, classification: dict[str, Any], question: str) -> dict[str, Any]:
        return self.compiler.default_plan_from_classification(classification, question)

    def should_use_default_plan_from_classification(self, classification: dict[str, Any]) -> bool:
        return self.compiler.should_use_default_plan_from_classification(classification)

    def merge_classification_and_plan(self, classification: dict[str, Any], plan: dict[str, Any], question: str) -> dict[str, Any]:
        return self.compiler.merge_classification_and_plan(classification, plan, question)

    def fallback_execution_task(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self.compiler.fallback_execution_task(payload)

    def normalize_planner_contract(
        self,
        payload: dict[str, Any],
        role: str,
        role_policies: Any | None = None,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        payload["time_requirement"] = time_requirement_from_payload(payload)
        payload["knowledge_requirement"] = self.normalize_knowledge_requirement(payload.get("knowledge_requirement") or {})

        message_type = str(payload.get("message_type") or "business_question")
        route = str(payload.get("route") or "rag")
        selected_tool = str(payload.get("selected_tool") or "") or None
        selected_action = str(payload.get("selected_action") or (payload.get("tool_input") or {}).get("action") or "") or None
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
        raw_execution_plan = payload.get("execution_plan") if isinstance(payload.get("execution_plan"), dict) else {}
        raw_tasks = raw_execution_plan.get("tasks") if isinstance(raw_execution_plan.get("tasks"), list) else payload.get("tasks")
        has_explicit_tasks = bool(raw_tasks)
        payload["execution_plan"] = self.execution_plan_from_payload(payload)
        tasks = list((payload.get("execution_plan") or {}).get("tasks") or [])
        repair_execution_plan_time_contract(payload, tasks)
        if maybe_add_calendar_query_task(payload, tasks):
            payload["normalization_reason"] = "calendar query task completed from mixed datetime request"
        if maybe_add_query_first_update_task(payload, tasks):
            payload["normalization_reason"] = "calendar update task completed from query-first request"
        payload["execution_plan"]["tasks"] = tasks

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

        if (
            payload["time_requirement"].get("requires_current_datetime")
            and not tasks
            and message_type != "smalltalk"
            and str(payload.get("context_usage") or "") != "use_previous_tool_context"
        ):
            payload = self.force_current_datetime_tool_plan(payload)
            route = str(payload.get("route") or "tool")
            selected_tool = str(payload.get("selected_tool") or "") or None
            selected_action = str(payload.get("selected_action") or "") or None
            tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
            raw_tasks = (payload.get("execution_plan") or {}).get("tasks") if isinstance(payload.get("execution_plan"), dict) else []
            has_explicit_tasks = bool(raw_tasks)
            tasks = list(raw_tasks or [])

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
        if str(payload.get("context_usage") or "") == "use_previous_tool_context" and not selected_tool and previous_context.get("tool_name"):
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
            fallback_task = self.fallback_execution_task(payload)
            payload["execution_plan"] = {"tasks": [fallback_task] if fallback_task else [], "strategy": str(payload.get("reason") or "")}
            route = "tool"

        if selected_tool and route == "direct":
            payload["route"] = "tool"
            payload.setdefault("normalization_reason", "selected tool implies tool route")
            fallback_task = self.fallback_execution_task(payload)
            payload["execution_plan"] = {"tasks": [fallback_task] if fallback_task else [], "strategy": str(payload.get("reason") or "")}
            route = "tool"

        gated_payload = apply_capability_gates(
            payload,
            tasks,
            role=role,
            tool_registry=self.tool_registry,
            role_policies=role_policies,
            state=state,
        )
        if gated_payload is not None:
            return gated_payload

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
                payload["tool_input"] = tool_input
            return payload

        if route not in {"direct", "reject"}:
            payload["route"] = "direct"
        return payload

    @staticmethod
    def force_current_datetime_tool_plan(payload: dict[str, Any]) -> dict[str, Any]:
        return PlanCompiler.force_current_datetime_tool_plan(payload)

    def calendar_write_needs_clarification(
        self,
        payload: dict[str, Any],
        tasks: list[dict[str, Any]],
        state: dict[str, Any] | None = None,
        role: str | None = None,
        role_policies: Any | None = None,
    ) -> bool:
        previous_context = (state or {}).get("previous_tool_context") if state is not None else {}
        allowed_actions = self.tool_registry.allowed_actions(
            "manage_company_calendar",
            role or (state or {}).get("role"),
            role_policies=role_policies,
        )
        return calendar_write_target_needs_clarification(
            payload,
            tasks,
            previous_tool_context=previous_context if isinstance(previous_context, dict) else {},
            allowed_actions=allowed_actions,
        )

    @staticmethod
    def has_executable_calendar_query_source(tasks: list[dict[str, Any]]) -> bool:
        return calendar_has_executable_query_source(tasks)

    def first_disallowed_tool_task(
        self,
        tasks: list[dict[str, Any]],
        role: str,
        role_policies: Any | None = None,
    ) -> dict[str, Any] | None:
        return first_disallowed_tool_task(
            tasks,
            role,
            tool_registry=self.tool_registry,
            role_policies=role_policies,
        )
