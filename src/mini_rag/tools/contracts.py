from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _validate_iso_date(value: str | None, field_name: str) -> str | None:
    if value is None:
        return value
    try:
        date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc
    return str(value)


class DateTimeInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timezone: str = "Asia/Shanghai"


class AttendanceInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start_date: str
    end_date: str
    department: str = "all"
    employee_name: str | None = None
    group_by: Literal["none", "department", "employee"] = "department"
    status_filter: Literal["present", "late", "leave", "absent"] | None = None
    include_records: bool = False

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _validate_iso_date(value, "date") or value


class CalendarInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["query", "create", "update", "delete"]

    # query
    start_date: str | None = None
    end_date: str | None = None
    event_type: str = "all"

    # create / update / delete
    event_id: str | None = None
    title: str | None = None
    type: Literal["meeting", "training", "payday", "holiday", "activity", "maintenance", "other"] = "other"
    date: str | None = None
    time: str | None = None
    department: str = "all"
    location: str = ""
    description: str = ""

    @field_validator("start_date", "end_date", "date")
    @classmethod
    def validate_optional_date(cls, value: str | None) -> str | None:
        return _validate_iso_date(value, "date")

    @model_validator(mode="after")
    def validate_by_action(self) -> "CalendarInput":
        if self.action == "query":
            if not self.start_date or not self.end_date:
                raise ValueError("query requires start_date and end_date")
        elif self.action == "create":
            if not self.title:
                raise ValueError("create requires title")
            if not self.date:
                raise ValueError("create requires date")
            if not self.time:
                raise ValueError("create requires time")
        elif self.action in {"update", "delete"}:
            if not self.event_id:
                raise ValueError(f"{self.action} requires event_id")
        return self


TOOL_INPUT_MODELS: dict[str, type[BaseModel]] = {
    "get_current_datetime": DateTimeInput,
    "query_attendance_summary": AttendanceInput,
    "manage_company_calendar": CalendarInput,
}


def get_tool_input_schema(tool_name: str) -> dict[str, Any]:
    return TOOL_INPUT_MODELS[tool_name].model_json_schema()


def validate_tool_input(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    model = TOOL_INPUT_MODELS[tool_name]
    validated = model(**payload)

    if tool_name == "manage_company_calendar":
        data = validated.model_dump(exclude_none=True)
        action = data.get("action")
        if action == "query":
            return {
                "action": "query",
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "event_type": data.get("event_type", "all"),
                "department": data.get("department", "all"),
            }
        if action == "create":
            return {
                "action": "create",
                "title": data["title"],
                "type": data.get("type", "other"),
                "date": data["date"],
                "time": data["time"],
                "department": data.get("department", "all"),
                "location": data.get("location", ""),
                "description": data.get("description", ""),
            }
        if action == "update":
            allowed = {"action", "event_id", "title", "type", "date", "time", "department", "location", "description"}
            return {k: v for k, v in data.items() if k in allowed}
        if action == "delete":
            return {"action": "delete", "event_id": data["event_id"]}

    return validated.model_dump(exclude_none=True)
