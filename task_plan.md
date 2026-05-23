# Enterprise Skill Runtime Plan

## Goal

Add a low-risk Enterprise Skill Runtime to the existing Agentic RAG mainline without changing the node order or RAG/tool semantics.

Mainline remains:
`build_runtime_context -> plan_with_llm -> resolve_plan_time -> validate_plan -> react_execute -> answer_with_llm -> update_memory`

## Phases

1. [complete] Inspect current tool execution, permissions, repositories, and tests.
2. [complete] Add failing tests/smoke coverage for registry, loader, executor, sample skills, and tool compatibility.
3. [complete] Implement `src/mini_rag/skills/` runtime and two example skills.
4. [complete] Add a minimal `skill.run` tool adapter without changing planner or executor semantics.
5. [complete] Add documentation and README references.
6. [complete] Verify with compileall, focused tests, smoke script, and selected regressions.

## Constraints

- Do not reorder or rewrite the Agentic RAG workflow.
- Do not change RAG Evidence Judge, RAG Reflect, TimeResolver, calendar/attendance safety, or Answer prompt.
- Do not turn skills into a global keyword-rule system.
- Load Skill Cards for discovery; load full `SKILL.md` only after selection.
- Execute skills through JSON stdin/stdout with timeout, cwd restricted to skill directory, schema validation, permission checks, and structured errors.

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
