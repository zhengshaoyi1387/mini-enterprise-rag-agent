from __future__ import annotations

import csv
import json
from pathlib import Path

from mini_rag.security.permissions import TOOL_ACTION_PERMISSIONS, TOOL_PERMISSIONS, get_allowed_tool_actions
from mini_rag.tools.attendance_tool import query_attendance_summary
from mini_rag.tools.calendar_tool import manage_company_calendar
from mini_rag.tools.daily_tools import build_default_tool_registry
from mini_rag.tools.datetime_tool import get_current_datetime


def write_attendance(path: Path) -> None:
    rows = [
        ["date", "employee_id", "name", "department", "status", "check_in", "check_out"],
        ["2026-05-01", "u001", "张三", "Engineering", "present", "09:02", "18:10"],
        ["2026-05-01", "u002", "李四", "Engineering", "late", "09:35", "18:05"],
        ["2026-05-01", "u003", "王五", "Sales", "leave", "", ""],
        ["2026-05-01", "u004", "赵六", "HR", "absent", "", ""],
        ["2026-05-02", "u001", "张三", "Engineering", "present", "09:00", "18:00"],
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)


def write_calendar(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260508-0001",
                    "date": "2026-05-08",
                    "title": "全员周会",
                    "type": "meeting",
                    "department": "all",
                    "time": "10:00-11:00",
                    "location": "线上会议",
                    "description": "每周全员同步",
                },
                {
                    "event_id": "EVT-20260513-0001",
                    "date": "2026-05-13",
                    "title": "新员工培训",
                    "type": "training",
                    "department": "Engineering",
                    "time": "14:00-16:00",
                    "location": "会议室 A",
                    "description": "面向本月入职员工",
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_get_current_datetime_returns_ranges() -> None:
    result = get_current_datetime({"timezone": "Asia/Shanghai"})

    assert result["timezone"] == "Asia/Shanghai"
    assert result["current_date"]
    assert result["current_time"]
    assert result["weekday"]
    assert result["weekday_zh"]
    assert {"today", "last_week", "next_week", "this_month"} <= set(result["ranges"])
    assert all("days" not in value for value in result["ranges"].values())
    assert set(result["ranges"]["today"]) == {"start_date", "end_date"}


def test_query_attendance_summary_basic(tmp_path: Path) -> None:
    file_path = tmp_path / "attendance.csv"
    write_attendance(file_path)

    result = query_attendance_summary(
        {
            "start_date": "2026-05-01",
            "end_date": "2026-05-02",
            "department": "all",
            "group_by": "none",
            "file_path": str(file_path),
        }
    )

    assert result["summary"]["total_records"] == 5
    assert result["summary"]["present"] == 2
    assert result["summary"]["late"] == 1
    assert result["summary"]["leave"] == 1
    assert result["summary"]["absent"] == 1
    assert result["summary"]["attendance_rate"] == "60.00%"
    assert result["summary"]["late_rate"] == "20.00%"
    assert "by_employee" not in result


def test_query_attendance_summary_group_by_department(tmp_path: Path) -> None:
    file_path = tmp_path / "attendance.csv"
    write_attendance(file_path)

    result = query_attendance_summary(
        {
            "start_date": "2026-05-01",
            "end_date": "2026-05-02",
            "group_by": "department",
            "file_path": str(file_path),
        }
    )

    by_department = {item["department"]: item for item in result["by_department"]}
    assert by_department["Engineering"]["total_records"] == 3
    assert by_department["Engineering"]["present"] == 2
    assert by_department["Engineering"]["late"] == 1
    assert by_department["Engineering"]["attendance_rate"] == "100.00%"
    assert by_department["HR"]["absent"] == 1


def test_query_attendance_summary_multi_status_filters_include_records(tmp_path: Path) -> None:
    file_path = tmp_path / "attendance.csv"
    write_attendance(file_path)

    result = query_attendance_summary(
        {
            "start_date": "2026-05-01",
            "end_date": "2026-05-02",
            "department": "all",
            "group_by": "department",
            "status_filters": ["late", "leave", "absent"],
            "include_records": True,
            "file_path": str(file_path),
        }
    )

    assert result["filtered_count"] == 3
    assert result["filtered_count_by_status"] == {"late": 1, "leave": 1, "absent": 1}
    assert {record["status"] for record in result["records"]} == {"late", "leave", "absent"}


def test_manage_company_calendar_query(tmp_path: Path) -> None:
    file_path = tmp_path / "company_calendar.json"
    write_calendar(file_path)

    result = manage_company_calendar(
        {
            "action": "query",
            "role": "employee",
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "department": "Engineering",
            "file_path": str(file_path),
        }
    )

    assert result["action"] == "query"
    assert [event["title"] for event in result["events"]] == ["新员工培训"]


def test_manage_company_calendar_query_scope_does_not_override_event_type(tmp_path: Path) -> None:
    file_path = tmp_path / "company_calendar.json"
    write_calendar(file_path)

    result = manage_company_calendar(
        {
            "action": "query",
            "role": "employee",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "query_scope": "all_events",
            "event_type": "training",
            "department": "all",
            "file_path": str(file_path),
        }
    )

    assert result["event_type"] == "training"
    assert [event["type"] for event in result["events"]] == ["training"]


def test_manage_company_calendar_events_include_weekday_without_persisting(tmp_path: Path) -> None:
    file_path = tmp_path / "company_calendar.json"
    file_path.write_text(
        json.dumps(
            [
                {
                    "event_id": "EVT-20260518-0001",
                    "date": "2026-05-18",
                    "title": "周例会",
                    "type": "meeting",
                    "department": "all",
                    "time": "10:00-11:00",
                    "location": "线上",
                    "description": "",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    queried = manage_company_calendar(
        {
            "action": "query",
            "role": "employee",
            "start_date": "2026-05-18",
            "end_date": "2026-05-18",
            "file_path": str(file_path),
        }
    )
    assert queried["events"][0]["weekday_zh"] == "星期一"

    created = manage_company_calendar(
        {
            "action": "create",
            "role": "admin",
            "date": "2026-05-19",
            "title": "培训",
            "type": "training",
            "time": "14:00-16:00",
            "department": "all",
            "file_path": str(file_path),
        }
    )
    assert created["event"]["weekday_zh"] == "星期二"

    updated = manage_company_calendar(
        {
            "action": "update",
            "role": "admin",
            "event_id": created["event_id"],
            "date": "2026-05-20",
            "file_path": str(file_path),
        }
    )
    assert updated["event"]["weekday_zh"] == "星期三"
    assert all("weekday_zh" not in item for item in json.loads(file_path.read_text(encoding="utf-8")))


def test_manage_company_calendar_admin_create_update_delete(tmp_path: Path) -> None:
    file_path = tmp_path / "company_calendar.json"
    file_path.write_text("[]", encoding="utf-8")

    created = manage_company_calendar(
        {
            "action": "create",
            "role": "admin",
            "date": "2026-05-13",
            "title": "新员工培训",
            "type": "training",
            "time": "14:00-16:00",
            "department": "all",
            "location": "会议室 A",
            "description": "面向本月入职员工",
            "file_path": str(file_path),
        }
    )
    event_id = created["event_id"]
    assert created["status"] == "created"
    assert event_id == "EVT-20260513-0001"

    updated = manage_company_calendar(
        {
            "action": "update",
            "role": "admin",
            "event_id": event_id,
            "time": "15:00-17:00",
            "location": "会议室 B",
            "file_path": str(file_path),
        }
    )
    assert updated["status"] == "updated"
    assert updated["event"]["location"] == "会议室 B"

    deleted = manage_company_calendar({"action": "delete", "role": "admin", "event_id": event_id, "file_path": str(file_path)})
    assert deleted["status"] == "deleted"
    assert json.loads(file_path.read_text(encoding="utf-8")) == []


def test_manage_company_calendar_non_admin_cannot_write(tmp_path: Path) -> None:
    file_path = tmp_path / "company_calendar.json"
    file_path.write_text("[]", encoding="utf-8")

    for action in ["create", "update", "delete"]:
        result = manage_company_calendar(
            {
                "action": action,
                "role": "employee",
                "event_id": "EVT-20260513-0001",
                "date": "2026-05-13",
                "title": "新员工培训",
                "file_path": str(file_path),
            }
        )
        assert result["error"] == "permission denied"
        assert result["required_role"] == "admin"


def test_tool_registry_contains_real_daily_tools_and_skill_adapter() -> None:
    registry = build_default_tool_registry()
    names = {tool["name"] for tool in registry.list_tools()}

    assert {"search_knowledge_base", "get_current_datetime", "query_attendance_summary", "manage_company_calendar"} <= names
    assert "skill" in names
    assert not {
        "generate_weekly_report",
        "draft_email",
        "create_it_ticket",
        "check_reimbursement_rule",
        "generate_leave_request",
    } & names


def test_tool_permissions_cleanup() -> None:
    old_tools = {
        "summarize_sources",
        "compare_sources",
        "rewrite_query",
        "generate_study_plan",
        "generate_weekly_report",
        "draft_email",
        "create_it_ticket",
        "check_reimbursement_rule",
        "generate_leave_request",
    }
    assert not old_tools & set(TOOL_PERMISSIONS)
    assert set(TOOL_PERMISSIONS) >= {
        "search_knowledge_base",
        "get_current_datetime",
        "query_attendance_summary",
        "manage_company_calendar",
    }
    assert set(TOOL_ACTION_PERMISSIONS["manage_company_calendar"]) == {"query", "create", "update", "delete"}
    assert get_allowed_tool_actions("employee", "manage_company_calendar") == {"query"}
    assert get_allowed_tool_actions("admin", "manage_company_calendar") == {"query", "create", "update", "delete"}
