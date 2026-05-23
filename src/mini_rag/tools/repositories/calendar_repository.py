from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from mini_rag.infrastructure.db.sqlite import DEFAULT_ENTERPRISE_DB_PATH, connect, ensure_database

WEEKDAY_ZH = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def weekday_zh(value: Any) -> str | None:
    try:
        return WEEKDAY_ZH[date.fromisoformat(str(value or "")).weekday()]
    except ValueError:
        return None


def split_time_range(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text or text == "全天":
        return "", ""
    if "-" not in text:
        return text, ""
    start, end = text.split("-", 1)
    return start.strip(), end.strip()


class CalendarRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_ENTERPRISE_DB_PATH)
        ensure_database(self.db_path)

    def query_events(
        self,
        start_date: str,
        end_date: str,
        *,
        event_type: str = "all",
        department: str = "all",
    ) -> list[dict[str, Any]]:
        sql = [
            "SELECT event_id, owner_employee_id, title, description, event_date, start_time,",
            "end_time, location, event_type, department, created_at, updated_at",
            "FROM calendar_events WHERE event_date >= ? AND event_date <= ?",
        ]
        params: list[Any] = [start_date, end_date]
        if event_type != "all":
            sql.append("AND event_type = ?")
            params.append(event_type)
        if department != "all":
            sql.append("AND department IN ('all', ?)")
            params.append(department)
        sql.append("ORDER BY event_date ASC, start_time ASC, event_id ASC")
        with connect(self.db_path) as conn:
            rows = conn.execute(" ".join(sql), params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def create_event(self, event: dict[str, Any]) -> dict[str, Any]:
        event_date = str(event.get("date") or event.get("event_date") or "")
        event_id = str(event.get("event_id") or self.next_event_id(event_date))
        start_time, end_time = split_time_range(event.get("time"))
        record = {
            "event_id": event_id,
            "owner_employee_id": str(event.get("owner_employee_id") or "").strip() or None,
            "title": str(event.get("title") or "").strip(),
            "description": str(event.get("description") or "").strip(),
            "event_date": event_date,
            "start_time": start_time,
            "end_time": end_time,
            "location": str(event.get("location") or "").strip(),
            "event_type": str(event.get("type") or event.get("event_type") or "meeting").strip() or "meeting",
            "department": str(event.get("department") or "all").strip() or "all",
        }
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO calendar_events(
                    event_id, owner_employee_id, title, description, event_date,
                    start_time, end_time, location, event_type, department
                )
                VALUES(
                    :event_id, :owner_employee_id, :title, :description, :event_date,
                    :start_time, :end_time, :location, :event_type, :department
                )
                """,
                record,
            )
            conn.commit()
        created = self.get_event(event_id)
        if created is None:
            raise RuntimeError(f"created event not found: {event_id}")
        return created

    def update_event(self, event_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"title", "type", "date", "time", "department", "location", "description"}
        updates: dict[str, Any] = {}
        for field, value in fields.items():
            if field not in allowed:
                continue
            if field == "type":
                updates["event_type"] = str(value or "").strip()
            elif field == "date":
                updates["event_date"] = str(value or "").strip()
            elif field == "time":
                start_time, end_time = split_time_range(value)
                updates["start_time"] = start_time
                updates["end_time"] = end_time
            else:
                updates[field] = str(value or "").strip()
        if not updates:
            return self.get_event(event_id)
        assignments = ", ".join(f"{field} = ?" for field in updates)
        values = list(updates.values()) + [event_id]
        with connect(self.db_path) as conn:
            result = conn.execute(
                f"UPDATE calendar_events SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE event_id = ?",
                values,
            )
            conn.commit()
            if result.rowcount == 0:
                return None
        return self.get_event(event_id)

    def delete_event(self, event_id: str) -> bool:
        with connect(self.db_path) as conn:
            result = conn.execute("DELETE FROM calendar_events WHERE event_id = ?", (event_id,))
            conn.commit()
            return result.rowcount > 0

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT event_id, owner_employee_id, title, description, event_date,
                       start_time, end_time, location, event_type, department, created_at, updated_at
                FROM calendar_events WHERE event_id = ?
                """,
                (event_id,),
            ).fetchone()
        return self._row_to_event(row) if row else None

    def next_event_id(self, event_date: str) -> str:
        prefix = f"EVT-{event_date.replace('-', '')}-"
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT event_id FROM calendar_events WHERE event_id LIKE ?",
                (f"{prefix}%",),
            ).fetchall()
        max_index = 0
        for row in rows:
            try:
                max_index = max(max_index, int(str(row["event_id"]).rsplit("-", 1)[-1]))
            except ValueError:
                continue
        return f"{prefix}{max_index + 1:04d}"

    @staticmethod
    def _row_to_event(row: Any) -> dict[str, Any]:
        start_time = str(row["start_time"] or "")
        end_time = str(row["end_time"] or "")
        event_date = str(row["event_date"] or "")
        time_text = f"{start_time}-{end_time}" if start_time and end_time else (start_time or "全天")
        event = {
            "event_id": str(row["event_id"] or ""),
            "date": event_date,
            "title": str(row["title"] or ""),
            "type": str(row["event_type"] or ""),
            "department": str(row["department"] or "all"),
            "time": time_text,
            "location": str(row["location"] or ""),
            "description": str(row["description"] or ""),
            "owner_employee_id": str(row["owner_employee_id"] or ""),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }
        weekday = weekday_zh(event_date)
        if weekday:
            event["weekday_zh"] = weekday
        return event
