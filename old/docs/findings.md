# Findings

## Current Behavior

- `src/mini_rag/graph/nodes.py` currently imports `select_daily_tool_by_rule`.
- `understand_query` has a rule-based early return for daily tools, so daily tool questions can skip the LLM.
- `route` checks the rule again and can override route/selected_tool.
- `call_tool` builds payload mostly in code and sets `final_answer` directly from formatted tool result.
- `generate_answer` returns early for `route=tool`, so the LLM does not currently summarize successful tool results.

## Target Behavior

- Rules become candidate hints only.
- LLM returns `selected_tool`, `tool_input`, `needs_time_resolution`, and `relative_time`.
- Code validates required slots, resolves relative time using `get_current_datetime`, executes tools, and stores structured tool context.
- Successful tool results flow to `generate_answer` for natural-language response.

## 2026-05-09 Findings

- `ToolRegistry.format_tool_contracts_for_prompt()` currently ignores role and exposes all daily tools/actions to every planner call.
- `permissions.py` only has tool-level `TOOL_PERMISSIONS`; action-level calendar permissions are inside the calendar tool rather than exposed to the planner.
- `AgentState` lacks `message_type`, `context_usage`, and `selected_action`.
- `understand_query()` already avoids keyword candidates, but it does not pass role-filtered contracts or enforce selected action validity.
- `call_tool()` still uses `assert_tool_permission`; executor needs `assert_tool_action_permission`.
- Direct smalltalk and permission-required behavior should be controlled by planner schema and answer formatting, not hard-coded routing keywords.

## 2026-05-09 Trace Follow-up Bug

- Trace `agent_trace_20260509_214815_trace_d6182b1471c04bdc88cae367d53ff41c.json` shows the Planner correctly produced `message_type=followup_question`, `context_usage=use_previous_tool_context`, `selected_tool=manage_company_calendar`, `selected_action=query`, and concrete `start_date/end_date`.
- The same Planner output also incorrectly set `intent=direct` and `route=direct`.
- Because the graph trusted `route` more than the executable tool selection, `next_after_route()` skipped `call_tool`; `tool_result` and `current_tool_context` stayed empty.
- Root cause: there was no program-side Planner contract normalizer to resolve conflicting structured fields before routing.

## 2026-05-09 Relative Date Context Bug

- Trace `agent_trace_20260509_221545_trace_e0a5dd807a7f40ce9a46ed1e3fca9773.json` shows `下周的公司日程` used `previous_tool_context` to derive `2026-05-25 至 2026-06-01`.
- Planner set `needs_time_resolution=false` and no internal `get_current_datetime` call happened.
- Root cause: relative-date authority was still delegated to Planner/context. The state machine needed a current-message datetime middleware that detects relative time expressions before routing/tool execution and forces datetime-tool resolution.

## 2026-05-09 Permission Policy Consistency

- Backend permission checks can consume `tool.action` policy specs, but `SQLiteAuthStore.update_role_policy()` previously discarded them because it only accepted bare tool names.
- API schemas omitted the `public` role although `VALID_ROLES` and default role policies include it.
- Frontend admin role editor only saved bare tool names, so it could not express action-level permissions.
