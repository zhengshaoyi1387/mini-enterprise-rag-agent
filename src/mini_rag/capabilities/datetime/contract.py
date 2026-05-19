from mini_rag.core.contracts import CapabilityContract

DATETIME_CONTRACT = CapabilityContract(
    name="datetime",
    supported_intents=("datetime", "time_query", "daily_tool"),
    allowed_roles=("public", "guest", "user", "employee", "finance", "hr", "it", "admin"),
    required_slots=("timezone",),
    optional_slots=("time_expression",),
    read_actions=("resolve",),
    write_actions=(),
    validation_rules=("Relative dates are resolved by the datetime capability, not by the LLM.",),
    clarification_rules=("Ask for timezone only if user needs a non-default timezone and it is ambiguous.",),
    refusal_rules=(),
    answer_policy=("Use tool returned current_date/current_time/weekday_zh/ranges; do not recalculate final dates in answer.",),
)
