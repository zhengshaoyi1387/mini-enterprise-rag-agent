from mini_rag.core.contracts import CapabilityContract

RAG_QA_CONTRACT = CapabilityContract(
    name="rag_qa",
    supported_intents=("rag_fact", "rag_explain", "policy_qa"),
    allowed_roles=("public", "guest", "user", "employee", "finance", "hr", "it", "admin"),
    required_slots=("query",),
    optional_slots=("kb_ids", "top_k", "candidate_k"),
    read_actions=("retrieve", "answer"),
    write_actions=(),
    validation_rules=("Exclude noisy/eval/manifest files from clean expected sources.",),
    clarification_rules=("Ask for scope when the policy/document target is ambiguous.",),
    refusal_rules=("Refuse when there is no supporting evidence.",),
    answer_policy=("RAG answers may call LLM but must cite retrieved evidence and avoid fabricated citations.",),
)

