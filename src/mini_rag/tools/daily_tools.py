from __future__ import annotations

"""Real daily enterprise tools backed by local files.

The registry deliberately keeps only a few bounded tools. RAG retrieval remains
implemented by the graph's retrieve node as ``search_knowledge_base``.
"""

from mini_rag.tools.attendance_tool import query_attendance_summary
from mini_rag.tools.calendar_tool import manage_company_calendar
from mini_rag.tools.contracts import get_tool_input_schema
from mini_rag.tools.datetime_tool import get_current_datetime
from mini_rag.tools.registry import ToolRegistry

DATETIME_ACTION_CONTRACTS = {
    "*": {
        "input": {"timezone": "Asia/Shanghai"},
        "notes": [
            "获取当前日期、时间、星期和 today/yesterday/tomorrow/this_week/last_week/next_week/this_month/last_month/next_month。",
            "用户只问日期、时间、星期几时可作为最终 selected_tool。",
            "用户问考勤或公司日程等业务数据时，它只是内部相对时间解析依赖，不是最终 selected_tool。",
        ],
    }
}

ATTENDANCE_ACTION_CONTRACTS = {
    "*": {
        "required": ["start_date", "end_date"],
        "input": {
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
            "department": "all",
            "employee_name": None,
            "group_by": "none|department|employee",
            "status_filter": "present|late|leave|absent|null",
            "include_records": False,
        },
        "notes": [
            "用于考勤、出勤、迟到、缺勤、请假统计。",
            "默认只返回汇总；用户明确问谁/哪些人/某员工时，include_records=true 且 group_by=employee。",
        ],
    }
}

CALENDAR_ACTION_CONTRACTS = {
    "query": {
        "required": ["action", "start_date", "end_date"],
        "input": {
            "action": "query",
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
            "event_type": "all",
            "department": "all",
        },
        "notes": [
            "用于查询会议、培训、发薪日、放假、节假日、团建、公司安排、公司活动、公司日程。",
            "默认 event_type=all。",
            "用户问“公司有什么活动 / 有什么安排 / 有什么日程 / 这周有什么事 / 下周有什么活动”时，event_type=all。",
            "只有用户明确指定类别时才缩窄 event_type：会议/周会/高层会议=meeting；培训/新员工培训=training；工资/发薪/工资发放日=payday；放假/节假日=holiday；团建/文体活动/活动类事项=activity；系统维护/维护窗口=maintenance。",
        ],
    },
    "create": {
        "required": ["action", "title", "date", "time"],
        "input": {
            "action": "create",
            "title": "...",
            "type": "meeting|training|payday|holiday|activity|maintenance|other",
            "date": "YYYY-MM-DD",
            "time": "HH:MM-HH:MM or HH:MM or 全天",
            "department": "all",
            "location": "",
            "description": "",
        },
        "notes": ["仅 admin 可见和可用。创建使用 date/time，不使用 start_date/end_date。"],
    },
    "update": {
        "required": ["action", "event_id"],
        "input": {
            "action": "update",
            "event_id": "EVT-...",
            "title": "...",
            "type": "meeting|training|payday|holiday|activity|maintenance|other",
            "date": "YYYY-MM-DD",
            "time": "HH:MM-HH:MM or HH:MM or 全天",
            "department": "all",
            "location": "",
            "description": "",
        },
        "notes": ["仅 admin 可见和可用。"],
    },
    "delete": {
        "required": ["action", "event_id"],
        "input": {"action": "delete", "event_id": "EVT-..."},
        "notes": ["仅 admin 可见和可用。"],
    },
}


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        "get_current_datetime",
        get_current_datetime,
        "获取当前日期时间和常用相对日期范围。只用于纯日期时间问题，或作为其他业务工具的内部时间解析依赖。",
        "low",
        input_schema=get_tool_input_schema("get_current_datetime"),
        action_contracts=DATETIME_ACTION_CONTRACTS,
        examples=[
            {"user": "今天星期几？", "tool_input": {"timezone": "Asia/Shanghai"}},
        ],
    )

    registry.register(
        "query_attendance_summary",
        query_attendance_summary,
        "读取本地 CSV 并统计企业考勤情况；适用于出勤、迟到、缺勤、请假统计等问题。",
        "medium",
        input_schema=get_tool_input_schema("query_attendance_summary"),
        action_contracts=ATTENDANCE_ACTION_CONTRACTS,
        examples=[
            {
                "user": "昨天公司的出勤情况如何？",
                "tool_input": {
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD",
                    "department": "all",
                    "group_by": "department",
                },
            },
            {
                "user": "谁迟到了？",
                "tool_input": {
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD",
                    "department": "all",
                    "group_by": "employee",
                    "status_filter": "late",
                    "include_records": True,
                },
            },
        ],
    )

    registry.register(
        "manage_company_calendar",
        manage_company_calendar,
        "查询、新增、更新或删除本地 JSON 公司日程；适用于公司活动、会议、培训、发薪日、放假、团建等日程问题。",
        "medium",
        input_schema=get_tool_input_schema("manage_company_calendar"),
        action_contracts=CALENDAR_ACTION_CONTRACTS,
        examples=[
            {
                "user": "下周公司有哪些安排？",
                "tool_input": {
                    "action": "query",
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD",
                    "event_type": "all",
                    "department": "all",
                },
            },
            {
                "user": "增加一项公司活动：下周三下午两点到四点，公司高层会议",
                "tool_input": {
                    "action": "create",
                    "title": "公司高层会议",
                    "type": "meeting",
                    "date": "YYYY-MM-DD",
                    "time": "14:00-16:00",
                    "department": "all",
                    "location": "",
                    "description": "",
                },
            },
        ],
    )

    return registry


def select_daily_tool_by_rule(query: str) -> str | None:
    """Deprecated compatibility shim.

    Tool routing is handled by the permission-aware LLM planner. This function
    intentionally returns None so keyword rules cannot influence routing.
    """
    _ = query
    return None
