from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_rag.infrastructure.db.sqlite import DEFAULT_ENTERPRISE_DB_PATH, connect, ensure_database


class AttendanceRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_ENTERPRISE_DB_PATH)
        ensure_database(self.db_path)

    def query_records(
        self,
        start_date: str,
        end_date: str,
        *,
        department: str = "all",
        employee_name: str | None = None,
        status_filters: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        sql = [
            "SELECT r.record_date, r.employee_id, e.name, e.department, r.status,",
            "r.check_in, r.check_out, r.reason, r.created_at",
            "FROM attendance_records r",
            "JOIN employees e ON e.employee_id = r.employee_id",
            "WHERE r.record_date >= ? AND r.record_date <= ?",
        ]
        params: list[Any] = [start_date, end_date]
        if department != "all":
            sql.append("AND e.department = ?")
            params.append(department)
        if employee_name:
            sql.append("AND e.name = ?")
            params.append(employee_name)
        if status_filters:
            placeholders = ",".join("?" for _ in status_filters)
            sql.append(f"AND r.status IN ({placeholders})")
            params.extend(status_filters)
        sql.append("ORDER BY r.record_date ASC, e.department ASC, e.name ASC")
        with connect(self.db_path) as conn:
            rows = conn.execute(" ".join(sql), params).fetchall()
        return [
            {
                "date": str(row["record_date"] or ""),
                "employee_id": str(row["employee_id"] or ""),
                "name": str(row["name"] or ""),
                "department": str(row["department"] or ""),
                "status": str(row["status"] or ""),
                "check_in": str(row["check_in"] or ""),
                "check_out": str(row["check_out"] or ""),
                "reason": str(row["reason"] or ""),
                "created_at": str(row["created_at"] or ""),
            }
            for row in rows
        ]

