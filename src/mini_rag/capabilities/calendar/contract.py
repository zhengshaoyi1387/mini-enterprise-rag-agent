from mini_rag.core.contracts import CapabilityContract

CALENDAR_QUERY_CONTRACT = CapabilityContract(
    name="calendar_query",
    supported_intents=("calendar_query", "daily_tool"),
    allowed_roles=("user", "employee", "finance", "hr", "it", "admin"),
    required_slots=("start_date", "end_date"),
    optional_slots=("event_type", "department"),
    read_actions=("query",),
    write_actions=(),
    validation_rules=("Dates entering the real query tool must be YYYY-MM-DD.",),
    clarification_rules=("Ask for a date or date range when it cannot be resolved deterministically.",),
    refusal_rules=("Refuse roles without calendar query permission.",),
    answer_policy=("Show only returned date, weekday_zh, time, title, and location for calendar event lists.",),
)

CALENDAR_WRITE_CONTRACT = CapabilityContract(
    name="calendar_write",
    supported_intents=("calendar_create", "calendar_update", "calendar_delete", "calendar_write"),
    allowed_roles=("admin",),
    required_slots=("action",),
    optional_slots=("event_id", "selector", "title", "date", "time", "location", "description"),
    read_actions=("query",),
    write_actions=("create", "update", "delete"),
    validation_rules=(
        "create requires title, date, and time before any real write.",
        "update/delete require a concrete event_id or a prior query for deterministic resolution.",
        "event_id placeholders such as all/multiple/event_id_from_x must never enter real write tools.",
    ),
    clarification_rules=(
        "Multiple matched update/delete candidates require clarification unless user said all or a concrete ordinal.",
        "Missing create/update/delete critical slots require clarification.",
    ),
    refusal_rules=("Non-admin roles cannot create, update, or delete company calendar events.",),
    answer_policy=("Template write results from verified tool output; do not let LLM alter write status.",),
)

