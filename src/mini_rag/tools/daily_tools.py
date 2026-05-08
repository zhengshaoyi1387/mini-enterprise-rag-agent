from __future__ import annotations

"""Real daily enterprise tools backed by local files.

The registry deliberately keeps only a few bounded tools. RAG retrieval remains
implemented by the graph's retrieve node as ``search_knowledge_base``.
"""

from mini_rag.tools.attendance_tool import query_attendance_summary
from mini_rag.tools.calendar_tool import manage_company_calendar
from mini_rag.tools.datetime_tool import get_current_datetime
from mini_rag.tools.registry import ToolRegistry

ATTENDANCE_KEYWORDS = ["出勤", "考勤", "迟到", "请假人数", "缺勤", "打卡"]
CALENDAR_KEYWORDS = ["日程", "安排", "会议", "培训", "发薪", "工资发放", "节假日", "放假", "团建", "公司活动"]
DATETIME_KEYWORDS = ["今天", "昨天", "明天", "上周", "下周", "本周", "本月", "上个月", "下个月", "现在几点", "当前日期", "星期几"]


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        "get_current_datetime",
        get_current_datetime,
        "获取当前日期时间和常用相对日期范围",
        "low",
        input_schema=GET_CURRENT_DATETIME_SCHEMA,
        examples=[
            {
                "user": "今天星期几？",
                "tool_input": {"timezone": "Asia/Shanghai"},
            }
        ],
    )

    registry.register(
        "query_attendance_summary",
        query_attendance_summary,
        "读取本地 CSV 并统计企业考勤情况",
        "medium",
        input_schema=ATTENDANCE_SCHEMA,
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
        "查询或管理本地 JSON 公司日程",
        "medium",
        input_schema=CALENDAR_SCHEMA,
        examples=CALENDAR_EXAMPLES,
    )

    return registry


def select_daily_tool_by_rule(query: str) -> str | None:
    q = str(query or "").lower()
    if any(word in q for word in ATTENDANCE_KEYWORDS):
        return "query_attendance_summary"
    if any(word in q for word in CALENDAR_KEYWORDS):
        return "manage_company_calendar"
    if any(word in q for word in DATETIME_KEYWORDS):
        return "get_current_datetime"
    return None

GET_CURRENT_DATETIME_SCHEMA = {
    "type": "object",
    "properties": {
        "timezone": {
            "type": "string",
            "default": "Asia/Shanghai",
            "description": "IANA timezone name.",
        }
    },
    "required": [],
}


ATTENDANCE_SCHEMA = {
    "type": "object",
    "description": "Query attendance records from local CSV.",
    "properties": {
        "start_date": {
            "type": "string",
            "format": "YYYY-MM-DD",
            "description": "Start date, inclusive.",
        },
        "end_date": {
            "type": "string",
            "format": "YYYY-MM-DD",
            "description": "End date, inclusive.",
        },
        "department": {
            "type": "string",
            "default": "all",
        },
        "employee_name": {
            "type": ["string", "null"],
            "default": None,
        },
        "group_by": {
            "type": "string",
            "enum": ["none", "department", "employee"],
            "default": "department",
        },
        "status_filter": {
            "type": ["string", "null"],
            "enum": ["present", "late", "leave", "absent", None],
            "default": None,
        },
        "include_records": {
            "type": "boolean",
            "default": False,
            "description": "Only true when user explicitly asks who/which employees.",
        },
    },
    "required": ["start_date", "end_date"],
}


CALENDAR_SCHEMA = {
    "type": "object",
    "description": "Query or manage company calendar events stored in local JSON.",
    "action_enum": ["query", "create", "update", "delete"],
    "action_mapping": {
        "查询/查看/有哪些安排/有没有培训/什么时候发工资": "query",
        "增加/添加/新增/创建": "create",
        "修改/调整/改成/更新": "update",
        "删除/取消/移除": "delete",
    },
    "hard_rules": [
        "action must be exactly one of query/create/update/delete.",
        "Never output action=add/new/insert/modify/edit/remove.",
        "For create, use date and time. Do not use start_date/end_date.",
        "For query, use start_date and end_date.",
        "Use time='HH:MM-HH:MM' instead of start_time/end_time.",
        "Do not invent location. If user does not provide location, use empty string.",
    ],
    "schemas_by_action": {
        "query": {
            "required": ["action", "start_date", "end_date"],
            "properties": {
                "action": {"const": "query"},
                "start_date": {"type": "string", "format": "YYYY-MM-DD"},
                "end_date": {"type": "string", "format": "YYYY-MM-DD"},
                "event_type": {"type": "string", "default": "all"},
                "department": {"type": "string", "default": "all"},
            },
        },
        "create": {
            "required": ["action", "title", "date", "time"],
            "forbidden": ["start_date", "end_date", "start_time", "end_time"],
            "properties": {
                "action": {"const": "create"},
                "title": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": [
                        "meeting",
                        "training",
                        "payday",
                        "holiday",
                        "activity",
                        "maintenance",
                        "other",
                    ],
                    "default": "other",
                },
                "date": {"type": "string", "format": "YYYY-MM-DD"},
                "time": {"type": "string", "examples": ["14:00-16:00", "全天"]},
                "department": {"type": "string", "default": "all"},
                "location": {"type": "string", "default": ""},
                "description": {"type": "string", "default": ""},
                "date_hint": {
                    "type": "string",
                    "description": "Optional weekday hint such as monday/tuesday/wednesday when date needs relative resolution.",
                },
            },
        },
        "update": {
            "required": ["action", "event_id"],
            "properties": {
                "action": {"const": "update"},
                "event_id": {"type": "string"},
                "title": {"type": "string"},
                "type": {"type": "string"},
                "date": {"type": "string", "format": "YYYY-MM-DD"},
                "time": {"type": "string"},
                "department": {"type": "string"},
                "location": {"type": "string"},
                "description": {"type": "string"},
            },
        },
        "delete": {
            "required": ["action", "event_id"],
            "properties": {
                "action": {"const": "delete"},
                "event_id": {"type": "string"},
            },
        },
    },
}


CALENDAR_EXAMPLES = [
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
            "date_hint": "wednesday",
        },
    },
    {
        "bad_tool_input": {
            "action": "add",
            "start_time": "14:00",
            "end_time": "16:00",
        },
        "why_bad": "action=add is invalid; use action=create. Use time='14:00-16:00'.",
    },
]