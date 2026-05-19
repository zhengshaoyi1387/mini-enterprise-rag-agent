# Task Plan: LLM Tool Planning Upgrade

## Goal
Replace keyword-rule direct daily tool routing with LLM tool planning, program-side validation/execution, relative-time resolution, and lightweight previous_tool_context.

## 2026-05-09 Goal
Upgrade the agent into a permission-aware capability-catalog architecture:

- Planner sees only tools/actions allowed for the current role.
- ToolRegistry exposes compact role-filtered contracts.
- Permissions support action-level checks.
- Planner schema separates message_type/context_usage/intent/route/tool/action.
- ToolExecutor still enforces final action permissions.
- Smalltalk and permission-required responses stay direct and do not inherit previous_tool_context.

## Phases

1. [complete] Inspect current Graph/tool/context behavior and write failing tests.
2. [complete] Implement state and prompt changes for candidate_tool and previous_tool_context.
3. [complete] Refactor nodes.py: no early return, no route override, build validated tool payload from LLM tool_input.
4. [complete] Extend attendance tool with status_filter/include_records.
5. [complete] Save current_tool_context in trace and load it as previous_tool_context.
6. [complete] Update docs.
7. [complete] Run target tests, full pytest, compileall.
8. [complete] Add red tests for permission-aware capability catalog and action-level planning.
9. [complete] Implement TOOL_ACTION_PERMISSIONS and role-filtered ToolRegistry contracts.
10. [complete] Update planner prompt/state/nodes for message_type, context_usage, selected_action.
11. [complete] Update executor permission middleware and friendly denial answers.
12. [complete] Update docs and run full verification.
13. [complete] Fix Planner contract inconsistency where an allowed selected_tool/action can be paired with route=direct and skip tool execution.
14. [complete] Add current datetime middleware so relative dates in the current message always resolve through get_current_datetime.
15. [complete] Align role policy storage and admin UI with action-level tool permissions.

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
