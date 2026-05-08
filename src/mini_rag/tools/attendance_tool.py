from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ATTENDANCE_FILE = Path("data/business/attendance.csv")
STATUSES = ("present", "late", "leave", "absent")


def _parse_date(value: Any, field_name: str) -> date | dict[str, str]:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return {"error": "invalid date format", "field": field_name, "expected": "YYYY-MM-DD"}


def _empty_counter() -> dict[str, int]:
    return {"total_records": 0, **{status: 0 for status in STATUSES}}


def _format_summary(counter: dict[str, int]) -> dict[str, Any]:
    total = int(counter.get("total_records", 0))
    summary: dict[str, Any] = {key: int(counter.get(key, 0)) for key in ["total_records", *STATUSES]}
    present_like = summary["present"] + summary["late"]
    summary["attendance_rate"] = f"{(present_like / total * 100) if total else 0:.2f}%"
    summary["late_rate"] = f"{(summary['late'] / total * 100) if total else 0:.2f}%"
    return summary


def _add(counter: dict[str, int], status: str) -> None:
    counter["total_records"] += 1
    if status in STATUSES:
        counter[status] += 1


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def query_attendance_summary(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    file_path = Path(str(payload.get("file_path") or ATTENDANCE_FILE))
    if not file_path.exists():
        return {"error": "attendance data file not found", "file_path": str(file_path)}

    start = _parse_date(payload.get("start_date"), "start_date")
    if isinstance(start, dict):
        return start
    end = _parse_date(payload.get("end_date"), "end_date")
    if isinstance(end, dict):
        return end
    if start > end:
        return {"error": "invalid date range", "message": "start_date must be <= end_date"}

    department = str(payload.get("department") or "all").strip() or "all"
    employee_name = payload.get("employee_name")
    employee_name = str(employee_name).strip() if employee_name not in (None, "") else None
    group_by = str(payload.get("group_by") or "department").strip().lower()
    if group_by not in {"none", "department", "employee"}:
        group_by = "department"
    status_filter = payload.get("status_filter")
    status_filter = str(status_filter).strip().lower() if status_filter not in (None, "") else None
    if status_filter and status_filter not in STATUSES:
        return {"error": "invalid status_filter", "allowed_statuses": list(STATUSES)}
    include_records = _as_bool(payload.get("include_records", False))

    total = _empty_counter()
    by_department: dict[str, dict[str, int]] = defaultdict(_empty_counter)
    by_employee: dict[tuple[str, str, str], dict[str, int]] = defaultdict(_empty_counter)
    filtered_records: list[dict[str, Any]] = []

    with file_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_date = _parse_date(row.get("date"), "date")
            if isinstance(row_date, dict):
                continue
            if row_date < start or row_date > end:
                continue
            row_department = str(row.get("department") or "").strip()
            row_name = str(row.get("name") or "").strip()
            if department != "all" and row_department != department:
                continue
            if employee_name and row_name != employee_name:
                continue
            status = str(row.get("status") or "").strip().lower()
            _add(total, status)
            _add(by_department[row_department or "-"], status)
            employee_key = (str(row.get("employee_id") or "").strip(), row_name or "-", row_department or "-")
            _add(by_employee[employee_key], status)
            if status_filter and status != status_filter:
                continue
            if include_records and (status_filter or employee_name):
                filtered_records.append(
                    {
                        "date": str(row.get("date") or ""),
                        "employee_id": str(row.get("employee_id") or ""),
                        "name": row_name,
                        "department": row_department,
                        "status": status,
                        "check_in": str(row.get("check_in") or ""),
                        "check_out": str(row.get("check_out") or ""),
                    }
                )

    result: dict[str, Any] = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "filters": {
            "department": department,
            "employee_name": employee_name,
            "group_by": group_by,
            "status_filter": status_filter,
            "include_records": include_records,
        },
        "summary": _format_summary(total),
    }
    if status_filter:
        result["status_filter"] = status_filter
        result["filtered_count"] = len(filtered_records) if include_records else int(total.get(status_filter, 0))
    if include_records and (status_filter or employee_name):
        result["records"] = filtered_records
    if group_by == "department":
        result["by_department"] = [
            {"department": key, **_format_summary(counter)}
            for key, counter in sorted(by_department.items(), key=lambda item: item[0])
        ]
    if group_by == "employee" or employee_name:
        result["by_employee"] = [
            {"employee_id": employee_id, "name": name, "department": dept, **_format_summary(counter)}
            for (employee_id, name, dept), counter in sorted(by_employee.items(), key=lambda item: (item[0][2], item[0][1]))
        ]
    return result
