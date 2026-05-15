from __future__ import annotations

"""Real daily enterprise tools backed by local files."""

from mini_rag.tools.attendance_tool import query_attendance_summary
from mini_rag.tools.calendar_tool import manage_company_calendar
from mini_rag.tools.contracts import get_tool_input_schema
from mini_rag.tools.datetime_tool import get_current_datetime
from mini_rag.tools.registry import ToolRegistry


def _search_knowledge_base_registry_placeholder(_payload: dict) -> dict:
    return {
        "error": "search_knowledge_base is executed by the RAG retrieval node",
        "tool_name": "search_knowledge_base",
        "risk_level": "low",
    }


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        "search_knowledge_base",
        _search_knowledge_base_registry_placeholder,
        "Unstructured enterprise knowledge base retrieval for policies, processes, FAQ and product documents. Executed by the RAG route.",
        "low",
        input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
        action_contracts={"*": {"in": {"query": "standalone enterprise knowledge question"}}},
    )

    registry.register(
        "get_current_datetime",
        get_current_datetime,
        "Current date/time and canonical relative ranges. Final tool only for pure date/time questions; internal dependency for business time references.",
        "low",
        input_schema=get_tool_input_schema("get_current_datetime"),
        action_contracts={"*": {"in": {"timezone": "default Asia/Shanghai"}}},
    )

    registry.register(
        "query_attendance_summary",
        query_attendance_summary,
        "Structured attendance query: presence, late, leave, absent statistics or records.",
        "medium",
        input_schema=get_tool_input_schema("query_attendance_summary"),
        action_contracts={
            "*": {
                "in": {
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD",
                    "department": "all|name",
                    "employee_name": "optional",
                    "group_by": "none|department|employee",
                    "status_filter": "present|late|leave|absent|null",
                    "include_records": "bool",
                }
            }
        },
    )

    registry.register(
        "manage_company_calendar",
        manage_company_calendar,
        "Structured company calendar. Query events or admin-only write events.",
        "medium",
        input_schema=get_tool_input_schema("manage_company_calendar"),
        action_contracts={
            "query": {
                "in": {
                    "action": "query",
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD",
                    "query_scope": "all_events|type_filtered",
                    "event_type": "all|meeting|training|payday|holiday|activity|maintenance|other",
                    "department": "all|name",
                },
                "semantics": "event_type is only a filter. For broad calendar/schedule/event queries use query_scope=all_events and event_type=all.",
            },
            "create": {
                "in": {
                    "action": "create",
                    "title": "string",
                    "type": "meeting|training|payday|holiday|activity|maintenance|other",
                    "date": "YYYY-MM-DD",
                    "time": "HH:MM-HH:MM|全天",
                    "department": "all|name",
                    "location": "string",
                    "description": "string",
                }
            },
            "update": {"in": {"action": "update", "event_id": "id", "fields": "title/type/date/time/department/location/description"}},
            "delete": {"in": {"action": "delete", "event_id": "id"}},
        },
    )

    return registry


def select_daily_tool_by_rule(_question: str) -> None:
    """Deprecated compatibility shim.

    Tool selection is now owned by the Planner and the permission-aware tool
    contract catalog. Keeping this function returning ``None`` avoids breaking
    older imports while ensuring no keyword/rule fast path can override the LLM
    plan.
    """

    return None
