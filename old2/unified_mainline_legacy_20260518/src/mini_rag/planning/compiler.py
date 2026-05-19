from __future__ import annotations

import re
from typing import Any

from mini_rag.capabilities.datetime.resolver import time_requirement_from_payload
from mini_rag.graph.utils import coerce_list


class PlanCompiler:
    """Compile classifier/planner payloads into compact executable plans.

    This layer performs schema-level normalization only. Capability-specific
    permissions, slot gates, date gates, and write-target resolution remain in
    validators/resolvers.
    """

    @staticmethod
    def normalize_knowledge_requirement(value: Any) -> dict[str, Any]:
        value = value if isinstance(value, dict) else {}
        return {
            "requires_company_knowledge": bool(value.get("requires_company_knowledge")),
            "known_from_user_message": bool(value.get("known_from_user_message")),
            "should_use_rag": bool(value.get("should_use_rag")),
        }

    def execution_plan_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        value = payload.get("execution_plan") if isinstance(payload.get("execution_plan"), dict) else {}
        raw_tasks = value.get("tasks") if isinstance(value.get("tasks"), list) else None
        if raw_tasks is None:
            raw_tasks = payload.get("tasks") if isinstance(payload.get("tasks"), list) else None
        tasks = [self.normalize_execution_task(task, idx) for idx, task in enumerate(raw_tasks or [])]
        tasks = [task for task in tasks if task.get("kind")]
        if not tasks:
            fallback = self.fallback_execution_task(payload)
            if fallback:
                tasks = [fallback]
        return {"tasks": tasks, "strategy": str(value.get("strategy") or payload.get("reason") or "").strip()}

    @staticmethod
    def normalize_execution_task(task: Any, idx: int) -> dict[str, Any]:
        task = task if isinstance(task, dict) else {}
        kind = str(task.get("kind") or task.get("type") or task.get("route") or "").strip().lower()
        tool = str(task.get("tool") or task.get("tool_name") or task.get("selected_tool") or "").strip() or None
        action = str(task.get("action") or task.get("selected_action") or "").strip() or None
        if not kind:
            if tool:
                kind = "tool"
            elif task.get("query"):
                kind = "rag"
        if kind not in {"rag", "tool", "direct"}:
            kind = ""
        args = task.get("args") if isinstance(task.get("args"), dict) else {}
        tool_input = task.get("tool_input") if isinstance(task.get("tool_input"), dict) else dict(args)
        if not action and isinstance(tool_input, dict):
            action = str(tool_input.get("action") or "").strip() or None
        if tool == "manage_company_calendar" and str(action or tool_input.get("action") or "").strip().lower() == "query":
            query_date = str(tool_input.get("date") or "").strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", query_date):
                tool_input = dict(tool_input)
                tool_input.pop("date", None)
                tool_input.setdefault("start_date", query_date)
                tool_input.setdefault("end_date", query_date)
        time_requirement = time_requirement_from_payload(task)
        normalized = {
            "task_id": str(task.get("task_id") or task.get("id") or f"t{idx + 1}"),
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

    def normalize_classification_payload(self, payload: dict[str, Any], question: str) -> dict[str, Any]:
        payload = dict(payload or {})
        route = str(payload.get("route") or "rag").strip().lower()
        if route not in {"direct", "rag", "tool", "reject"}:
            route = "rag"
        message_type = str(payload.get("message_type") or "business_question").strip() or "business_question"
        selected_tool = str(payload.get("selected_tool") or "").strip() or None
        selected_action = str(payload.get("selected_action") or "").strip() or None
        time_requirement = time_requirement_from_payload(payload)
        knowledge_requirement = self.normalize_knowledge_requirement(payload.get("knowledge_requirement") or {})

        if message_type == "smalltalk":
            route = "direct"
            payload["intent"] = "smalltalk"
            selected_tool = None
            selected_action = None
            knowledge_requirement = {"requires_company_knowledge": False, "known_from_user_message": True, "should_use_rag": False}

        if selected_tool and route == "direct" and message_type != "smalltalk":
            route = "tool"
            if payload.get("intent") in {None, "", "direct"}:
                payload["intent"] = "daily_tool"

        payload.update(
            {
                "message_type": message_type,
                "context_usage": str(payload.get("context_usage") or "none"),
                "intent": str(payload.get("intent") or ("daily_tool" if route == "tool" else "rag_fact" if route == "rag" else "direct")),
                "route": route,
                "standalone_query": str(payload.get("standalone_query") or question).strip() or question,
                "risk_level": str(payload.get("risk_level") or "low"),
                "selected_tool": selected_tool,
                "selected_action": selected_action,
                "time_requirement": time_requirement,
                "knowledge_requirement": knowledge_requirement,
                "reason": str(payload.get("reason") or ""),
            }
        )
        payload.pop("execution_plan", None)
        payload.pop("tasks", None)
        payload.pop("tool_input", None)
        return payload

    def default_plan_from_classification(self, classification: dict[str, Any], question: str) -> dict[str, Any]:
        payload = dict(classification or {})
        route = str(payload.get("route") or "rag")
        selected_tool = str(payload.get("selected_tool") or "").strip()
        selected_action = str(payload.get("selected_action") or "").strip()
        standalone = str(payload.get("standalone_query") or question).strip() or question
        time_requirement = time_requirement_from_payload(payload)
        tasks: list[dict[str, Any]] = []
        if route == "rag":
            tasks = [{"task_id": "t1", "kind": "rag", "objective": standalone, "query": standalone}]
        elif route == "tool" and selected_tool:
            existing_tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
            tool_input: dict[str, Any] = dict(existing_tool_input)
            if selected_tool == "get_current_datetime":
                selected_action = selected_action or "*"
                tool_input = {"timezone": tool_input.get("timezone") or "Asia/Shanghai"}
            elif selected_action and not tool_input:
                tool_input = {"action": selected_action}
            elif selected_action and selected_tool == "manage_company_calendar":
                tool_input.setdefault("action", selected_action)
            tasks = [
                {
                    "task_id": "t1",
                    "kind": "tool",
                    "objective": standalone,
                    "tool": selected_tool,
                    "action": selected_action or "*",
                    "tool_input": tool_input,
                    "time_requirement": time_requirement,
                }
            ]
        payload["execution_plan"] = {"tasks": tasks, "strategy": "short" if tasks else ""}
        if selected_tool:
            payload["selected_tool"] = selected_tool
        if selected_action:
            payload["selected_action"] = selected_action
        return payload

    def should_use_default_plan_from_classification(self, classification: dict[str, Any]) -> bool:
        classification = dict(classification or {})
        if str(classification.get("context_usage") or "none") == "use_previous_tool_context":
            return False
        route = str(classification.get("route") or "").strip().lower()
        selected_tool = str(classification.get("selected_tool") or "").strip()
        selected_action = str(classification.get("selected_action") or "").strip()
        intent = str(classification.get("intent") or "").strip()
        time_requirement = time_requirement_from_payload(classification)
        knowledge_requirement = self.normalize_knowledge_requirement(classification.get("knowledge_requirement") or {})
        entities = [str(x).strip() for x in coerce_list(classification.get("entities")) if str(x).strip()]

        if route in {"direct", "reject"} and not selected_tool:
            return True
        if (
            route == "tool"
            and selected_tool == "get_current_datetime"
            and selected_action in {"", "*"}
            and not knowledge_requirement.get("requires_company_knowledge")
            and not knowledge_requirement.get("should_use_rag")
        ):
            return True
        if (
            route == "rag"
            and intent in {"", "rag_fact", "policy_qa"}
            and not selected_tool
            and not time_requirement.get("requires_current_datetime")
            and len(entities) <= 1
        ):
            return True
        return False

    def merge_classification_and_plan(self, classification: dict[str, Any], plan: dict[str, Any], question: str) -> dict[str, Any]:
        classification = self.normalize_classification_payload(classification or {}, question=question)
        plan = dict(plan or {})
        merged = dict(classification)
        for key in (
            "message_type",
            "context_usage",
            "intent",
            "route",
            "standalone_query",
            "risk_level",
            "selected_tool",
            "selected_action",
            "tool_input",
            "required_tools",
            "time_requirement",
            "knowledge_requirement",
            "missing_required_slots",
            "topic",
            "entities",
            "reason",
        ):
            if key in plan and plan.get(key) not in (None, "", {}, []):
                merged[key] = plan.get(key)

        if "execution_plan" in plan:
            merged["execution_plan"] = plan.get("execution_plan")
        elif "tasks" in plan:
            merged["execution_plan"] = {"tasks": plan.get("tasks") or [], "strategy": plan.get("strategy") or "short"}
        else:
            merged = self.default_plan_from_classification(merged, question=question)

        tasks = list((merged.get("execution_plan") or {}).get("tasks") or [])
        first_tool_task = next((task for task in tasks if isinstance(task, dict) and str(task.get("kind") or "").lower() == "tool"), None)
        if first_tool_task:
            merged["route"] = "tool"
            if merged.get("intent") in {None, "", "direct"}:
                merged["intent"] = "daily_tool"
            existing_action = str(merged.get("selected_action") or "").strip().lower()
            first_action = str(first_tool_task.get("action") or (first_tool_task.get("tool_input") or {}).get("action") or "").strip().lower()
            preserve_write_intent = existing_action in {"create", "update", "delete"} and first_action == "query"
            merged["selected_tool"] = str(first_tool_task.get("tool") or merged.get("selected_tool") or "") or None
            if not preserve_write_intent:
                merged["selected_action"] = str(first_tool_task.get("action") or merged.get("selected_action") or "") or None
            if isinstance(first_tool_task.get("tool_input"), dict) and not preserve_write_intent:
                merged["tool_input"] = dict(first_tool_task.get("tool_input") or {})
        elif tasks and any(isinstance(task, dict) and str(task.get("kind") or "").lower() == "rag" for task in tasks):
            merged["route"] = "rag"
            if merged.get("intent") in {None, "", "direct", "daily_tool"}:
                merged["intent"] = "rag_fact"
            merged["selected_tool"] = None
            merged["selected_action"] = None
        return merged

    @staticmethod
    def fallback_execution_task(payload: dict[str, Any]) -> dict[str, Any] | None:
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
                "time_requirement": time_requirement_from_payload(payload),
                "depends_on": [],
            }
        if route == "rag":
            return {
                "task_id": "t1",
                "kind": "rag",
                "objective": standalone or "查询企业知识库",
                "query": standalone,
                "tool_input": {},
                "time_requirement": time_requirement_from_payload(payload),
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
                "time_requirement": time_requirement_from_payload(payload),
                "depends_on": [],
            }
        return None

    @staticmethod
    def force_current_datetime_tool_plan(payload: dict[str, Any]) -> dict[str, Any]:
        standalone = str(payload.get("standalone_query") or payload.get("question") or "当前日期和时间").strip() or "当前日期和时间"
        time_requirement = time_requirement_from_payload(payload)
        task = {
            "task_id": "t1",
            "kind": "tool",
            "objective": "获取当前日期和时间",
            "tool": "get_current_datetime",
            "action": "*",
            "tool_input": {"timezone": "Asia/Shanghai"},
            "time_requirement": time_requirement,
        }
        payload.update(
            {
                "route": "tool",
                "intent": "daily_tool" if payload.get("intent") in {None, "", "direct"} else payload.get("intent"),
                "standalone_query": standalone,
                "selected_tool": "get_current_datetime",
                "selected_action": "*",
                "tool_input": {"timezone": "Asia/Shanghai"},
                "required_tools": ["get_current_datetime"],
                "execution_plan": {"tasks": [task], "strategy": str(payload.get("reason") or "short")},
                "normalization_reason": "current datetime requires get_current_datetime tool",
            }
        )
        return payload
