from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_rag.infrastructure.db.sqlite import DEFAULT_ENTERPRISE_DB_PATH, connect, ensure_database

EMPLOYEES: list[dict[str, str]] = [
    {"employee_id": "u001", "name": "张三", "department": "研发部", "role": "employee", "manager": "王经理", "status": "active"},
    {"employee_id": "u002", "name": "李四", "department": "研发部", "role": "employee", "manager": "王经理", "status": "active"},
    {"employee_id": "u003", "name": "王五", "department": "销售部", "role": "employee", "manager": "陈经理", "status": "active"},
    {"employee_id": "u004", "name": "赵六", "department": "HR", "role": "hr", "manager": "刘经理", "status": "active"},
    {"employee_id": "u005", "name": "孙七", "department": "产品部", "role": "employee", "manager": "周经理", "status": "active"},
    {"employee_id": "u006", "name": "周八", "department": "产品部", "role": "employee", "manager": "周经理", "status": "active"},
]

CALENDAR_EVENTS: list[dict[str, str]] = [
    {"event_id": "EVT-20260508-0001", "event_date": "2026-05-08", "title": "全员周会", "event_type": "meeting", "department": "all", "start_time": "10:00", "end_time": "11:00", "location": "线上会议", "description": "每周全员同步"},
    {"event_id": "EVT-20260513-0001", "event_date": "2026-05-13", "title": "新员工培训", "event_type": "training", "department": "all", "start_time": "14:00", "end_time": "16:00", "location": "会议室 A", "description": "面向本月入职员工"},
    {"event_id": "EVT-20260515-0001", "event_date": "2026-05-15", "title": "工资发放日", "event_type": "payday", "department": "all", "start_time": "", "end_time": "", "location": "", "description": "本月工资发放"},
    {"event_id": "EVT-20260515-0002", "event_date": "2026-05-15", "title": "公司团建", "event_type": "activity", "department": "all", "start_time": "16:00", "end_time": "18:00", "location": "城市公园", "description": "五月团队建设活动"},
    {"event_id": "EVT-20260516-0001", "event_date": "2026-05-16", "title": "公司团建", "event_type": "activity", "department": "all", "start_time": "21:00", "end_time": "22:00", "location": "会议室A", "description": "临时团建复盘"},
    {"event_id": "EVT-20260517-0001", "event_date": "2026-05-17", "title": "公司会议", "event_type": "meeting", "department": "all", "start_time": "08:00", "end_time": "10:00", "location": "会议室", "description": "公司会议"},
    {"event_id": "EVT-20260518-0001", "event_date": "2026-05-18", "title": "产品部 OKR 同步会", "event_type": "meeting", "department": "产品部", "start_time": "10:00", "end_time": "11:00", "location": "会议室 B", "description": "产品部 OKR 对齐"},
    {"event_id": "EVT-20260518-0002", "event_date": "2026-05-18", "title": "研发部周会", "event_type": "meeting", "department": "研发部", "start_time": "14:00", "end_time": "15:00", "location": "会议室 C", "description": "研发进度同步"},
    {"event_id": "EVT-20260519-0001", "event_date": "2026-05-19", "title": "公司团建", "event_type": "activity", "department": "all", "start_time": "16:00", "end_time": "18:00", "location": "城市公园", "description": "下周第一个团建活动，用于 update/delete 评测"},
    {"event_id": "EVT-20260520-0001", "event_date": "2026-05-20", "title": "产品培训", "event_type": "training", "department": "产品部", "start_time": "09:00", "end_time": "11:00", "location": "培训室 1", "description": "产品部培训安排"},
    {"event_id": "EVT-20260520-0002", "event_date": "2026-05-20", "title": "项目复盘会", "event_type": "meeting", "department": "all", "start_time": "10:00", "end_time": "11:00", "location": "", "description": "后天的公司会议，用于 SQLite smoke"},
    {"event_id": "EVT-20260521-0001", "event_date": "2026-05-21", "title": "季度经营复盘", "event_type": "meeting", "department": "all", "start_time": "14:00", "end_time": "15:00", "location": "会议室 A", "description": "固定 ID，用于 update/delete 评测"},
    {"event_id": "EVT-20260521-0002", "event_date": "2026-05-21", "title": "公司团建", "event_type": "activity", "department": "all", "start_time": "18:00", "end_time": "20:00", "location": "团建餐厅", "description": "第二个团建活动"},
    {"event_id": "EVT-20260522-0001", "event_date": "2026-05-22", "title": "研发安全培训", "event_type": "training", "department": "研发部", "start_time": "10:00", "end_time": "11:00", "location": "线上会议室", "description": "研发安全培训"},
    {"event_id": "EVT-20260522-0002", "event_date": "2026-05-22", "title": "客户项目同步", "event_type": "meeting", "department": "销售部", "start_time": "15:00", "end_time": "16:00", "location": "会议室 B", "description": "固定 ID，用于更新为客户复盘会"},
    {"event_id": "EVT-20260523-0001", "event_date": "2026-05-23", "title": "招聘面试安排同步", "event_type": "meeting", "department": "HR", "start_time": "09:00", "end_time": "10:00", "location": "会议室 D", "description": "HR 面试流程同步"},
    {"event_id": "EVT-20260524-0001", "event_date": "2026-05-24", "title": "新员工产品培训", "event_type": "training", "department": "产品部", "start_time": "10:00", "end_time": "12:00", "location": "培训室 2", "description": "用于 query-first update 评测"},
    {"event_id": "EVT-20260531-0001", "event_date": "2026-05-31", "title": "OKR 季度复盘", "event_type": "meeting", "department": "all", "start_time": "16:00", "end_time": "17:00", "location": "线上会议", "description": "标题包含 OKR，用于关键词查询评测"},
]

ATTENDANCE_ROWS: list[dict[str, str]] = [
    {"record_date": date, "employee_id": employee_id, "status": status, "check_in": check_in, "check_out": check_out}
    for date, employee_id, status, check_in, check_out in [
        ("2026-05-01", "u001", "present", "09:00", "18:00"), ("2026-05-01", "u002", "late", "09:35", "18:05"), ("2026-05-01", "u003", "leave", "", ""), ("2026-05-01", "u004", "absent", "", ""), ("2026-05-01", "u005", "present", "09:00", "18:00"), ("2026-05-01", "u006", "late", "09:28", "18:02"),
        ("2026-05-04", "u001", "present", "09:00", "18:00"), ("2026-05-04", "u002", "late", "09:31", "18:00"), ("2026-05-04", "u003", "present", "09:00", "18:00"), ("2026-05-04", "u004", "leave", "", ""), ("2026-05-04", "u005", "present", "09:00", "18:00"), ("2026-05-04", "u006", "present", "09:00", "18:00"),
        ("2026-05-05", "u001", "present", "09:00", "18:00"), ("2026-05-05", "u002", "present", "09:00", "18:00"), ("2026-05-05", "u003", "absent", "", ""), ("2026-05-05", "u004", "present", "09:00", "18:00"), ("2026-05-05", "u005", "late", "09:26", "18:30"), ("2026-05-05", "u006", "present", "09:00", "18:00"),
        ("2026-05-06", "u001", "absent", "", ""), ("2026-05-06", "u002", "present", "09:00", "18:00"), ("2026-05-06", "u003", "present", "09:00", "18:00"), ("2026-05-06", "u004", "present", "09:00", "18:00"), ("2026-05-06", "u005", "present", "09:00", "18:00"), ("2026-05-06", "u006", "leave", "", ""),
        ("2026-05-07", "u001", "present", "09:00", "18:00"), ("2026-05-07", "u002", "leave", "", ""), ("2026-05-07", "u003", "present", "09:00", "18:00"), ("2026-05-07", "u004", "late", "09:22", "18:06"), ("2026-05-07", "u005", "leave", "", ""), ("2026-05-07", "u006", "present", "09:00", "18:00"),
        ("2026-05-08", "u001", "late", "09:29", "18:12"), ("2026-05-08", "u002", "present", "09:00", "18:00"), ("2026-05-08", "u003", "late", "09:34", "18:01"), ("2026-05-08", "u004", "present", "09:00", "18:00"), ("2026-05-08", "u005", "present", "09:00", "18:00"), ("2026-05-08", "u006", "present", "09:00", "18:00"),
        ("2026-05-11", "u001", "present", "09:00", "18:00"), ("2026-05-11", "u002", "present", "09:00", "18:00"), ("2026-05-11", "u003", "present", "09:00", "18:00"), ("2026-05-11", "u004", "present", "09:00", "18:00"), ("2026-05-11", "u005", "present", "09:00", "18:00"), ("2026-05-11", "u006", "late", "09:27", "18:05"),
        ("2026-05-12", "u001", "present", "09:00", "18:00"), ("2026-05-12", "u002", "absent", "", ""), ("2026-05-12", "u003", "present", "09:00", "18:00"), ("2026-05-12", "u004", "present", "09:00", "18:00"), ("2026-05-12", "u005", "late", "09:33", "18:20"), ("2026-05-12", "u006", "present", "09:00", "18:00"),
        ("2026-05-13", "u001", "present", "09:00", "18:00"), ("2026-05-13", "u002", "present", "09:00", "18:00"), ("2026-05-13", "u003", "present", "09:00", "18:00"), ("2026-05-13", "u004", "present", "09:00", "18:00"), ("2026-05-13", "u005", "present", "09:00", "18:00"), ("2026-05-13", "u006", "absent", "", ""),
        ("2026-05-14", "u001", "leave", "", ""), ("2026-05-14", "u002", "present", "09:00", "18:00"), ("2026-05-14", "u003", "late", "09:25", "18:04"), ("2026-05-14", "u004", "present", "09:00", "18:00"), ("2026-05-14", "u005", "present", "09:00", "18:00"), ("2026-05-14", "u006", "present", "09:00", "18:00"),
        ("2026-05-15", "u001", "present", "09:00", "18:00"), ("2026-05-15", "u002", "present", "09:00", "18:00"), ("2026-05-15", "u003", "present", "09:00", "18:00"), ("2026-05-15", "u004", "late", "09:32", "18:07"), ("2026-05-15", "u005", "present", "09:03", "18:10"), ("2026-05-15", "u006", "present", "09:00", "18:00"),
        ("2026-05-16", "u001", "present", "09:01", "18:05"), ("2026-05-16", "u002", "present", "09:02", "18:03"), ("2026-05-16", "u003", "present", "09:00", "18:00"), ("2026-05-16", "u004", "present", "09:00", "18:00"), ("2026-05-16", "u005", "late", "09:21", "18:06"), ("2026-05-16", "u006", "present", "09:00", "18:00"),
    ]
]


def initialize_enterprise_demo_db(db_path: str | Path | None = None, *, reset: bool = False) -> dict[str, Any]:
    path = Path(db_path or DEFAULT_ENTERPRISE_DB_PATH)
    if reset and path.exists():
        path.unlink()
    ensure_database(path)
    with connect(path) as conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO employees(employee_id, name, department, role, manager, status)
            VALUES(:employee_id, :name, :department, :role, :manager, :status)
            """,
            EMPLOYEES,
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO calendar_events(
                event_id, owner_employee_id, title, description, event_date, start_time,
                end_time, location, event_type, department
            )
            VALUES(
                :event_id, :owner_employee_id, :title, :description, :event_date,
                :start_time, :end_time, :location, :event_type, :department
            )
            """,
            [{**event, "owner_employee_id": event.get("owner_employee_id") or None} for event in CALENDAR_EVENTS],
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO attendance_records(employee_id, record_date, check_in, check_out, status, reason)
            VALUES(:employee_id, :record_date, :check_in, :check_out, :status, :reason)
            """,
            [{**row, "reason": row.get("reason", "")} for row in ATTENDANCE_ROWS],
        )
        conn.commit()
        counts = {
            "employees": conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0],
            "calendar_events": conn.execute("SELECT COUNT(*) FROM calendar_events").fetchone()[0],
            "attendance_records": conn.execute("SELECT COUNT(*) FROM attendance_records").fetchone()[0],
        }
    return {"db_path": str(path), **counts}


if __name__ == "__main__":
    print(initialize_enterprise_demo_db(reset=True))
