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

ATTENDANCE_KEYWORDS = ["出勤", "考勤", "迟到", "请假人数", "缺勤", "打卡"]
CALENDAR_KEYWORDS = ["日程", "安排", "会议", "培训", "发薪", "工资发放", "节假日", "放假", "团建", "公司活动"]
DATETIME_KEYWORDS = ["今天", "昨天", "明天", "上周", "下周", "本周", "本月", "上个月", "下个月", "现在几点", "当前日期", "星期几"]


def build_default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        "get_current_datetime",
        get_current_datetime,
        "获取当前日期时间和常用相对日期范围。只用于纯日期时间问题，或作为其他业务工具的内部时间解析依赖。",
        "low",
        input_schema=get_tool_input_schema("get_current_datetime"),
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
    q = str(query or "").lower()
    if any(word in q for word in ATTENDANCE_KEYWORDS):
        return "query_attendance_summary"
    if any(word in q for word in CALENDAR_KEYWORDS):
        return "manage_company_calendar"
    if any(word in q for word in DATETIME_KEYWORDS):
        return "get_current_datetime"
    return None
