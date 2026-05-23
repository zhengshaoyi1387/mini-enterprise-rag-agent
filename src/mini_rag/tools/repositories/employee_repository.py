from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_rag.infrastructure.db.sqlite import DEFAULT_ENTERPRISE_DB_PATH, connect, ensure_database


class EmployeeRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_ENTERPRISE_DB_PATH)
        ensure_database(self.db_path)

    def list_employees(self, *, department: str | None = None, status: str = "active") -> list[dict[str, Any]]:
        sql = "SELECT employee_id, name, department, role, manager, status FROM employees WHERE status = ?"
        params: list[Any] = [status]
        if department:
            sql += " AND department = ?"
            params.append(department)
        sql += " ORDER BY department ASC, name ASC"
        with connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get_employee(self, employee_id: str) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT employee_id, name, department, role, manager, status FROM employees WHERE employee_id = ?",
                (employee_id,),
            ).fetchone()
        return dict(row) if row else None
