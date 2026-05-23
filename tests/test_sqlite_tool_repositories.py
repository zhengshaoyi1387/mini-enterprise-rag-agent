from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mini_rag.api.app import app
from mini_rag.config import get_settings
from mini_rag.infrastructure.db.seed import initialize_enterprise_demo_db
from mini_rag.tools.contracts import validate_tool_input
from mini_rag.tools.attendance_tool import query_attendance_summary
from mini_rag.tools.calendar_tool import manage_company_calendar
from mini_rag.tools.repositories.attendance_repository import AttendanceRepository
from mini_rag.tools.repositories.calendar_repository import CalendarRepository
from mini_rag.tools.repositories.employee_repository import EmployeeRepository


def test_initialize_enterprise_demo_db_creates_core_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"

    result = initialize_enterprise_demo_db(db_path, reset=True)

    assert result["db_path"] == str(db_path)
    assert result["employees"] >= 6
    assert result["calendar_events"] >= 4
    assert result["attendance_records"] >= 10
    assert EmployeeRepository(db_path).list_employees()[0]["employee_id"]


def test_calendar_repository_queries_and_updates_concrete_event(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)
    repo = CalendarRepository(db_path)

    events = repo.query_events("2026-05-20", "2026-05-20", event_type="meeting")
    assert [event["event_id"] for event in events] == ["EVT-20260520-0002"]
    assert events[0]["date"] == "2026-05-20"
    assert events[0]["time"] == "10:00-11:00"
    assert events[0]["weekday_zh"] == "星期三"

    updated = repo.update_event("EVT-20260520-0002", {"location": "会议室B", "time": "15:00-16:00"})

    assert updated is not None
    assert updated["event_id"] == "EVT-20260520-0002"
    assert updated["location"] == "会议室B"
    assert updated["time"] == "15:00-16:00"


def test_attendance_repository_queries_last_week_anomalies(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)
    repo = AttendanceRepository(db_path)

    rows = repo.query_records(
        "2026-05-11",
        "2026-05-17",
        department="all",
        status_filters=["late", "leave", "absent"],
    )

    assert rows
    assert {row["status"] for row in rows} <= {"late", "leave", "absent"}
    assert any(row["department"] == "产品部" for row in rows)


def test_calendar_tool_uses_sqlite_backend_without_changing_return_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)

    queried = manage_company_calendar(
        {
            "action": "query",
            "role": "employee",
            "start_date": "2026-05-20",
            "end_date": "2026-05-20",
            "event_type": "meeting",
            "db_path": str(db_path),
        }
    )

    assert queried["action"] == "query"
    assert queried["event_type"] == "meeting"
    assert queried["events"][0]["event_id"] == "EVT-20260520-0002"
    assert {"event_id", "date", "time", "title", "location", "weekday_zh"} <= set(queried["events"][0])

    updated = manage_company_calendar(
        {
            "action": "update",
            "role": "admin",
            "event_id": "EVT-20260520-0002",
            "location": "多功能厅",
            "db_path": str(db_path),
        }
    )

    assert updated["status"] == "updated"
    assert updated["event"]["location"] == "多功能厅"
    assert updated["event"]["weekday_zh"] == "星期三"


def test_calendar_create_without_type_defaults_to_meeting_for_agent_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)

    payload = validate_tool_input(
        "manage_company_calendar",
        {
            "action": "create",
            "title": "加班会议",
            "date": "2026-05-22",
            "time": "20:00-20:30",
            "location": "会议室A",
            "description": "全体员工参加",
        },
    )
    created = manage_company_calendar({**payload, "role": "admin", "db_path": str(db_path)})

    assert created["status"] == "created"
    assert created["event"]["type"] == "meeting"

    queried = manage_company_calendar(
        {
            "action": "query",
            "role": "employee",
            "start_date": "2026-05-22",
            "end_date": "2026-05-22",
            "event_type": "meeting",
            "db_path": str(db_path),
        }
    )

    assert "加班会议" in {event["title"] for event in queried["events"]}


def test_attendance_tool_uses_sqlite_backend_without_changing_return_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)

    result = query_attendance_summary(
        {
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "department": "all",
            "group_by": "department",
            "status_filters": ["late", "leave", "absent"],
            "include_records": True,
            "db_path": str(db_path),
        }
    )

    assert result["summary"]["total_records"] > 0
    assert result["filtered_count"] == sum(result["filtered_count_by_status"].values())
    assert {"start_date", "end_date", "filters", "summary", "by_department", "records"} <= set(result)
    assert {record["status"] for record in result["records"]} <= {"late", "leave", "absent"}


def test_internal_tool_api_exposes_sqlite_adapter(tmp_path: Path) -> None:
    db_path = tmp_path / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=True)
    client = TestClient(app)

    headers = {"X-API-Key": get_settings().agent_api_key}
    events = client.get(
        "/internal/calendar/events",
        params={"start_date": "2026-05-20", "end_date": "2026-05-20", "event_type": "meeting", "db_path": str(db_path)},
        headers=headers,
    )
    assert events.status_code == 200
    assert events.json()["events"][0]["event_id"] == "EVT-20260520-0002"

    patched = client.patch(
        "/internal/calendar/events/EVT-20260520-0002",
        params={"db_path": str(db_path)},
        json={"location": "会议室Z"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["event"]["location"] == "会议室Z"

    attendance = client.get(
        "/internal/attendance/records",
        params={"start_date": "2026-05-11", "end_date": "2026-05-17", "db_path": str(db_path)},
        headers=headers,
    )
    assert attendance.status_code == 200
    assert attendance.json()["records"]
