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
