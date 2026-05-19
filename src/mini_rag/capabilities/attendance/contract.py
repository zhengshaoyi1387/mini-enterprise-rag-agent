from mini_rag.core.contracts import CapabilityContract

ATTENDANCE_CONTRACT = CapabilityContract(
    name="attendance_query",
    supported_intents=("attendance_query", "daily_tool"),
    allowed_roles=("employee", "finance", "hr", "it", "admin"),
    required_slots=("start_date", "end_date"),
    optional_slots=("department", "employee_name", "group_by", "status_filter", "status_filters", "include_records"),
    read_actions=("query",),
    write_actions=(),
    validation_rules=("Dates entering attendance query must be YYYY-MM-DD.", "Anomaly means late, leave, and absent."),
    clarification_rules=("Ask for date range if no deterministic time context exists.",),
    refusal_rules=("Refuse roles without attendance permission.",),
    answer_policy=("Template summaries and records from tool output; do not invent employees or counts.",),
)

