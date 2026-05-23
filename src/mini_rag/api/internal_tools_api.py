from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status

from mini_rag.config import get_settings
from mini_rag.infrastructure.db.seed import initialize_enterprise_demo_db
from mini_rag.tools.repositories.attendance_repository import AttendanceRepository
from mini_rag.tools.repositories.calendar_repository import CalendarRepository

router = APIRouter(prefix="/internal", tags=["internal-tools"])


def _require_internal_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if x_api_key != settings.agent_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid internal tool api key")


def _resolve_db_path(db_path: str | None) -> Path:
    settings = get_settings()
    path = Path(db_path or settings.enterprise_db_path)
    if not path.exists():
        initialize_enterprise_demo_db(path, reset=False)
    return path


@router.get("/calendar/events")
def list_calendar_events(
    start_date: str,
    end_date: str,
    event_type: str = "all",
    department: str = "all",
    db_path: str | None = Query(default=None),
    _auth: str | None = Header(default=None, alias="X-API-Key", include_in_schema=False),
) -> dict[str, Any]:
    _require_internal_key(_auth)
    path = _resolve_db_path(db_path)
    events = CalendarRepository(path).query_events(
        start_date,
        end_date,
        event_type=event_type or "all",
        department=department or "all",
    )
    return {"events": events, "count": len(events), "db_path": str(path)}


@router.patch("/calendar/events/{event_id}")
def patch_calendar_event(
    event_id: str,
    payload: dict[str, Any],
    db_path: str | None = Query(default=None),
    _auth: str | None = Header(default=None, alias="X-API-Key", include_in_schema=False),
) -> dict[str, Any]:
    _require_internal_key(_auth)
    path = _resolve_db_path(db_path)
    event = CalendarRepository(path).update_event(event_id, payload)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"event not found: {event_id}")
    return {"event": event, "db_path": str(path)}


@router.get("/attendance/records")
def list_attendance_records(
    start_date: str,
    end_date: str,
    department: str = "all",
    employee_name: str | None = None,
    status_filter: str | None = None,
    db_path: str | None = Query(default=None),
    _auth: str | None = Header(default=None, alias="X-API-Key", include_in_schema=False),
) -> dict[str, Any]:
    _require_internal_key(_auth)
    path = _resolve_db_path(db_path)
    status_filters = [status_filter] if status_filter else None
    records = AttendanceRepository(path).query_records(
        start_date,
        end_date,
        department=department or "all",
        employee_name=employee_name,
        status_filters=status_filters,
    )
    return {"records": records, "count": len(records), "db_path": str(path)}
