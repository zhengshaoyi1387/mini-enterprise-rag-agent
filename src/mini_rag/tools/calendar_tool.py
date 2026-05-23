from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from mini_rag.infrastructure.db.seed import initialize_enterprise_demo_db
from mini_rag.infrastructure.db.sqlite import DEFAULT_ENTERPRISE_DB_PATH
from mini_rag.tools.repositories.calendar_repository import CalendarRepository

CALENDAR_FILE = Path("data/business/company_calendar.json")
WRITE_ACTIONS = {"create", "update", "delete"}
QUERY_ROLES = {"user", "employee", "finance", "hr", "it", "admin"}
UPDATE_FIELDS = {"title", "type", "date", "time", "department", "location", "description"}
WEEKDAY_ZH = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


def _parse_date(value: Any, field_name: str) -> date | dict[str, str]:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return {"error": "invalid date format", "field": field_name, "expected": "YYYY-MM-DD"}


def _weekday_zh(value: Any) -> str | None:
    try:
        return WEEKDAY_ZH[date.fromisoformat(str(value or "")).weekday()]
    except ValueError:
        return None


def _with_weekday(event: dict[str, Any]) -> dict[str, Any]:
    output = dict(event)
    weekday = _weekday_zh(output.get("date"))
    if weekday:
        output["weekday_zh"] = weekday
    return output


def _ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("[]", encoding="utf-8")


def _read_events(path: Path) -> list[dict[str, Any]]:
    _ensure_file(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError:
        data = []
    return [item for item in data if isinstance(item, dict)]


def _write_events(path: Path, events: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


def _permission_error(action: str, role: str) -> dict[str, Any]:
    return {
        "action": action,
        "error": "permission denied",
        "role": role,
        "required_role": "admin" if action in WRITE_ACTIONS else "user/employee/finance/hr/it/admin",
    }


def _next_event_id(events: list[dict[str, Any]], event_date: str) -> str:
    prefix = f"EVT-{event_date.replace('-', '')}-"
    max_index = 0
    for event in events:
        event_id = str(event.get("event_id") or "")
        if event_id.startswith(prefix):
            try:
                max_index = max(max_index, int(event_id.rsplit("-", 1)[-1]))
            except ValueError:
                continue
    return f"{prefix}{max_index + 1:04d}"


def _role(payload: dict[str, Any]) -> str:
    return str(payload.get("role") or "guest").strip().lower() or "guest"


def _should_use_file_backend(payload: dict[str, Any]) -> bool:
    return bool(payload.get("file_path"))


def _repository(payload: dict[str, Any]) -> CalendarRepository:
    db_path = Path(str(payload.get("db_path") or DEFAULT_ENTERPRISE_DB_PATH))
    if not db_path.exists():
        initialize_enterprise_demo_db(db_path, reset=False)
    return CalendarRepository(db_path)


def manage_company_calendar(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    action = str(payload.get("action") or "query").strip().lower()
    if action not in {"query", "create", "update", "delete"}:
        return {"error": "unsupported action", "action": action}

    role = _role(payload)
    if action == "query" and role not in QUERY_ROLES:
        return _permission_error(action, role)
    if action in WRITE_ACTIONS and role != "admin":
        return _permission_error(action, role)

    if not _should_use_file_backend(payload):
        repo = _repository(payload)
        if action == "query":
            return _query_sqlite(payload, repo)
        if action == "create":
            return _create_sqlite(payload, repo)
        if action == "update":
            return _update_sqlite(payload, repo)
        return _delete_sqlite(payload, repo)

    file_path = Path(str(payload.get("file_path") or CALENDAR_FILE))
    events = _read_events(file_path)

    if action == "query":
        return _query(payload, events)
    if action == "create":
        return _create(payload, events, file_path)
    if action == "update":
        return _update(payload, events, file_path)
    return _delete(payload, events, file_path)


def _query(payload: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    start = _parse_date(payload.get("start_date"), "start_date")
    if isinstance(start, dict):
        return start
    end = _parse_date(payload.get("end_date"), "end_date")
    if isinstance(end, dict):
        return end
    if start > end:
        return {"error": "invalid date range", "message": "start_date must be <= end_date"}

    event_type = str(payload.get("event_type") or "all").strip() or "all"
    department = str(payload.get("department") or "all").strip() or "all"
    matched: list[dict[str, Any]] = []
    for event in events:
        event_date = _parse_date(event.get("date"), "date")
        if isinstance(event_date, dict) or event_date < start or event_date > end:
            continue
        if event_type != "all" and str(event.get("type") or "") != event_type:
            continue
        event_department = str(event.get("department") or "all")
        if department != "all" and event_department not in {"all", department}:
            continue
        matched.append(_with_weekday(event))
    matched.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("time") or ""), str(item.get("event_id") or "")))
    return {
        "action": "query",
        "risk_level": "low",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "event_type": event_type,
        "department": department,
        "events": matched,
    }


def _query_sqlite(payload: dict[str, Any], repo: CalendarRepository) -> dict[str, Any]:
    start = _parse_date(payload.get("start_date"), "start_date")
    if isinstance(start, dict):
        return start
    end = _parse_date(payload.get("end_date"), "end_date")
    if isinstance(end, dict):
        return end
    if start > end:
        return {"error": "invalid date range", "message": "start_date must be <= end_date"}
    event_type = str(payload.get("event_type") or "all").strip() or "all"
    department = str(payload.get("department") or "all").strip() or "all"
    return {
        "action": "query",
        "risk_level": "low",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "event_type": event_type,
        "department": department,
        "events": repo.query_events(start.isoformat(), end.isoformat(), event_type=event_type, department=department),
        "data_backend": "sqlite",
    }


def _create(payload: dict[str, Any], events: list[dict[str, Any]], file_path: Path) -> dict[str, Any]:
    event_date = _parse_date(payload.get("date"), "date")
    if isinstance(event_date, dict):
        return event_date
    event = {
        "event_id": _next_event_id(events, event_date.isoformat()),
        "date": event_date.isoformat(),
        "title": str(payload.get("title") or "").strip(),
        "type": str(payload.get("type") or "meeting").strip() or "meeting",
        "department": str(payload.get("department") or "all").strip() or "all",
        "time": str(payload.get("time") or "全天").strip() or "全天",
        "location": str(payload.get("location") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
    }
    if not event["title"]:
        return {"action": "create", "error": "title is required"}
    events.append(event)
    events.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("time") or ""), str(item.get("event_id") or "")))
    _write_events(file_path, events)
    return {
        "action": "create",
        "risk_level": "medium",
        "event_id": event["event_id"],
        "status": "created",
        "message": "公司日程已创建",
        "event": _with_weekday(event),
    }


def _create_sqlite(payload: dict[str, Any], repo: CalendarRepository) -> dict[str, Any]:
    event_date = _parse_date(payload.get("date"), "date")
    if isinstance(event_date, dict):
        return event_date
    event = {
        "date": event_date.isoformat(),
        "title": str(payload.get("title") or "").strip(),
        "type": str(payload.get("type") or "meeting").strip() or "meeting",
        "department": str(payload.get("department") or "all").strip() or "all",
        "time": str(payload.get("time") or "全天").strip() or "全天",
        "location": str(payload.get("location") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
    }
    if not event["title"]:
        return {"action": "create", "error": "title is required"}
    created = repo.create_event(event)
    return {
        "action": "create",
        "risk_level": "medium",
        "event_id": created["event_id"],
        "status": "created",
        "message": "公司日程已创建",
        "event": created,
        "data_backend": "sqlite",
    }


def _update(payload: dict[str, Any], events: list[dict[str, Any]], file_path: Path) -> dict[str, Any]:
    event_id = str(payload.get("event_id") or "").strip()
    for event in events:
        if str(event.get("event_id") or "") != event_id:
            continue
        for field in UPDATE_FIELDS:
            if field not in payload:
                continue
            if field == "date":
                parsed = _parse_date(payload.get(field), field)
                if isinstance(parsed, dict):
                    return parsed
                event[field] = parsed.isoformat()
            else:
                event[field] = str(payload.get(field) or "").strip()
        events.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("time") or ""), str(item.get("event_id") or "")))
        _write_events(file_path, events)
        return {
            "action": "update",
            "risk_level": "medium",
            "event_id": event_id,
            "status": "updated",
            "message": "公司日程已更新",
            "event": _with_weekday(event),
        }
    return {"action": "update", "event_id": event_id, "error": "event not found"}


def _update_sqlite(payload: dict[str, Any], repo: CalendarRepository) -> dict[str, Any]:
    event_id = str(payload.get("event_id") or "").strip()
    fields = {field: payload[field] for field in UPDATE_FIELDS if field in payload}
    updated = repo.update_event(event_id, fields)
    if updated is None:
        return {"action": "update", "event_id": event_id, "error": "event not found"}
    return {
        "action": "update",
        "risk_level": "medium",
        "event_id": event_id,
        "status": "updated",
        "message": "公司日程已更新",
        "event": updated,
        "data_backend": "sqlite",
    }


def _delete(payload: dict[str, Any], events: list[dict[str, Any]], file_path: Path) -> dict[str, Any]:
    event_id = str(payload.get("event_id") or "").strip()
    remaining = [event for event in events if str(event.get("event_id") or "") != event_id]
    if len(remaining) == len(events):
        return {"action": "delete", "event_id": event_id, "error": "event not found"}
    _write_events(file_path, remaining)
    return {"action": "delete", "risk_level": "medium", "event_id": event_id, "status": "deleted", "message": "公司日程已删除"}


def _delete_sqlite(payload: dict[str, Any], repo: CalendarRepository) -> dict[str, Any]:
    event_id = str(payload.get("event_id") or "").strip()
    if not repo.delete_event(event_id):
        return {"action": "delete", "event_id": event_id, "error": "event not found"}
    return {
        "action": "delete",
        "risk_level": "medium",
        "event_id": event_id,
        "status": "deleted",
        "message": "公司日程已删除",
        "data_backend": "sqlite",
    }
