from __future__ import annotations

from pathlib import Path

from mini_rag.infrastructure.db.seed import initialize_enterprise_demo_db
from mini_rag.tools.attendance_tool import query_attendance_summary
from mini_rag.tools.calendar_tool import manage_company_calendar


def main() -> None:
    db_path = Path("data/enterprise_demo.db")
    print(initialize_enterprise_demo_db(db_path, reset=False))

    calendar = manage_company_calendar(
        {
            "action": "query",
            "role": "employee",
            "start_date": "2026-05-20",
            "end_date": "2026-05-20",
            "event_type": "meeting",
            "db_path": str(db_path),
        }
    )
    print({"calendar_event_count": len(calendar.get("events", [])), "first_event": (calendar.get("events") or [{}])[0]})

    updated = manage_company_calendar(
        {
            "action": "update",
            "role": "admin",
            "event_id": "EVT-20260520-0002",
            "location": "会议室B",
            "db_path": str(db_path),
        }
    )
    print({"update_status": updated.get("status"), "event": updated.get("event")})

    attendance = query_attendance_summary(
        {
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "status_filters": ["late", "leave", "absent"],
            "include_records": True,
            "db_path": str(db_path),
        }
    )
    print({"attendance_summary": attendance.get("summary"), "filtered_count": attendance.get("filtered_count")})


if __name__ == "__main__":
    main()
