from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


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


class CalendarInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["query", "create", "update", "delete"]

    # query
    start_date: str | None = None
    end_date: str | None = None
    query_scope: Literal["all_events", "type_filtered"] = "all_events"
    event_type: Literal["all", "meeting", "training", "payday", "holiday", "activity", "maintenance", "other"] = "all"

    # create/update/delete
    event_id: str | None = None
    title: str | None = None
    type: Literal["meeting", "training", "payday", "holiday", "activity", "maintenance", "other"] = "other"
    date: str | None = None
    time: str | None = None
    department: str = "all"
    location: str = ""
    description: str = ""

    @model_validator(mode="after")
    def validate_by_action(self) -> "CalendarInput":
        if self.action == "query":
            if not self.start_date or not self.end_date:
                raise ValueError("query requires start_date and end_date")
            if self.query_scope == "all_events":
                self.event_type = "all"
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
    return model(**payload).model_dump(exclude_none=True)
