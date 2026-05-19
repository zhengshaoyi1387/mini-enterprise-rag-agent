from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ValidationStatus = Literal["valid", "needs_clarification", "refused", "skipped", "invalid"]
TaskStatus = Literal["ok", "error", "skipped", "needs_clarification", "refused", "no_evidence"]


@dataclass(frozen=True)
class DateRange:
    start_date: str = ""
    end_date: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"start_date": self.start_date, "end_date": self.end_date}


@dataclass(frozen=True)
class CapabilityContract:
    name: str
    supported_intents: tuple[str, ...]
    allowed_roles: tuple[str, ...]
    required_slots: tuple[str, ...] = ()
    optional_slots: tuple[str, ...] = ()
    read_actions: tuple[str, ...] = ()
    write_actions: tuple[str, ...] = ()
    validation_rules: tuple[str, ...] = ()
    clarification_rules: tuple[str, ...] = ()
    refusal_rules: tuple[str, ...] = ()
    answer_policy: tuple[str, ...] = ()


@dataclass(frozen=True)
class RequestContext:
    question: str
    role: str
    user_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    kb_ids: tuple[str, ...] = ()
    override_now: str | datetime | None = None
    time_context: "TimeContext | None" = None


@dataclass(frozen=True)
class TimeContext:
    timezone: str = "Asia/Shanghai"
    now: datetime | None = None
    today: str = ""
    yesterday: str = ""
    tomorrow: str = ""
    day_after_tomorrow: str = ""
    this_week: DateRange = field(default_factory=DateRange)
    last_week: DateRange = field(default_factory=DateRange)
    next_week: DateRange = field(default_factory=DateRange)
    this_month: DateRange = field(default_factory=DateRange)
    last_month: DateRange = field(default_factory=DateRange)
    next_month: DateRange = field(default_factory=DateRange)
    time_reference_type: Literal["none", "relative", "absolute", "range", "ambiguous"] = "none"
    absolute_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    requires_current_datetime: bool = False


@dataclass(frozen=True)
class PlannedTask:
    task_id: str
    kind: Literal["rag", "tool", "direct"]
    objective: str = ""
    tool: str | None = None
    action: str | None = None
    query: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    time_context: TimeContext = field(default_factory=TimeContext)
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidatePlan:
    route: Literal["direct", "rag", "tool", "reject"]
    intent: str
    tasks: tuple[PlannedTask, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class ExecutableTask(PlannedTask):
    validation_status: ValidationStatus = "valid"


@dataclass(frozen=True)
class ExecutablePlan:
    tasks: tuple[ExecutableTask, ...] = ()
    strategy: str = ""


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    layer: str
    task_id: str | None = None
    field: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus = "valid"
    issues: tuple[ValidationIssue, ...] = ()
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "valid"


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    kind: Literal["rag", "tool"]
    status: TaskStatus
    result_summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnswerPacket:
    route: Literal["direct", "rag", "tool", "reject"]
    status: ValidationStatus | TaskStatus | Literal["ready"] = "ready"
    messages: tuple[str, ...] = ()
    task_results: tuple[TaskResult, ...] = ()
    sources: tuple[dict[str, Any], ...] = ()
    should_call_llm: bool = False
