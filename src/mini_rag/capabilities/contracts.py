from mini_rag.capabilities.attendance.contract import ATTENDANCE_CONTRACT
from mini_rag.capabilities.calendar.contract import CALENDAR_QUERY_CONTRACT, CALENDAR_WRITE_CONTRACT
from mini_rag.capabilities.datetime.contract import DATETIME_CONTRACT
from mini_rag.capabilities.rag.contract import RAG_QA_CONTRACT
from mini_rag.core.contracts import CapabilityContract

MIXED_TASK_CONTRACT = CapabilityContract(
    name="mixed_task",
    supported_intents=("mixed_task", "multi_step"),
    allowed_roles=("employee", "finance", "hr", "it", "admin"),
    required_slots=(),
    optional_slots=("tasks",),
    read_actions=("compose",),
    write_actions=(),
    validation_rules=("Each child task must pass its own capability contract.",),
    clarification_rules=("Clarify when any write child task has an ambiguous target.",),
    refusal_rules=("Refuse any child task that violates permission.",),
    answer_policy=("Summarize child AnswerPackets; never pass raw state to the answer prompt.",),
)

CAPABILITY_CONTRACTS: tuple[CapabilityContract, ...] = (
    DATETIME_CONTRACT,
    CALENDAR_QUERY_CONTRACT,
    CALENDAR_WRITE_CONTRACT,
    ATTENDANCE_CONTRACT,
    RAG_QA_CONTRACT,
    MIXED_TASK_CONTRACT,
)

