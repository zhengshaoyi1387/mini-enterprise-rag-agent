# Task Plan: LLM Tool Planning Upgrade

## Goal
Replace keyword-rule direct daily tool routing with LLM tool planning, program-side validation/execution, relative-time resolution, and lightweight previous_tool_context.

## Phases

1. [complete] Inspect current Graph/tool/context behavior and write failing tests.
2. [complete] Implement state and prompt changes for candidate_tool and previous_tool_context.
3. [complete] Refactor nodes.py: no early return, no route override, build validated tool payload from LLM tool_input.
4. [complete] Extend attendance tool with status_filter/include_records.
5. [complete] Save current_tool_context in trace and load it as previous_tool_context.
6. [complete] Update docs.
7. [complete] Run target tests, full pytest, compileall.

## Constraints

- Do not reintroduce old mock tools.
- Do not let select_daily_tool_by_rule decide final route/tool.
- Do not let LLM guess concrete dates for relative time.
- Do not add database or pandas.
- Preserve RAG, auth, RBAC, trace, and audit behavior.

## Red Test Evidence

- Initial `tests/test_llm_tool_planning.py`: 8 failed, 1 passed.
- Failures confirm current architecture skips LLM for daily tools, route overrides LLM, lacks `tool_result` and `current_tool_context`, and exposes `invalid date format`.
- After implementation: `tests/test_llm_tool_planning.py`: 9 passed.
