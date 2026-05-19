from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class DateTimeInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    timezone: str = "Asia/Shanghai"
    override_now: str | None = None
    eval_fixed_now: str | None = None
    fixed_now: str | None = None


class AttendanceInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    start_date: str
    end_date: str
    department: str = "all"
    employee_name: str | None = None
    group_by: Literal["none", "department", "employee"] = "department"
    status_filter: Literal["present", "late", "leave", "absent"] | None = None
    status_filters: list[Literal["present", "late", "leave", "absent"]] | None = None
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
    value = model(**payload)
    data = value.model_dump(exclude_none=True)
    if tool_name == "manage_company_calendar" and isinstance(value, CalendarInput):
        provided = set(value.model_fields_set)
        if value.action == "update":
            allowed_update_fields = {"title", "type", "date", "time", "department", "location", "description"}
            keep = {"action", "event_id"} | (provided & allowed_update_fields)
            data = {key: field_value for key, field_value in data.items() if key in keep}
        elif value.action == "delete":
            data = {key: field_value for key, field_value in data.items() if key in {"action", "event_id"}}
    return data
