# Progress

## 2026-05-08

- Started LLM tool planning upgrade.
- Read relevant process skills and confirmed current architecture issue.
- Created planning files for this multi-step refactor.
- Added failing tests in `tests/test_llm_tool_planning.py`.
- Red run: `8 failed, 1 passed`; failures match expected architecture gaps.
- Implemented candidate-only daily rule hints, LLM tool_plan parsing, validated tool payload execution, relative-time resolution, and current/previous tool context plumbing.
- Extended attendance tool with `status_filter` and `include_records`.
- Target run: `tests/test_llm_tool_planning.py` passed with `9 passed`.
- Full run after code changes: `85 passed`.
- Updated README, ARCHITECTURE, and INTERVIEW_GUIDE with LLM tool planning and previous_tool_context flow.
- Removed unused hard-coded calendar/date inference helpers from `nodes.py`.
- Final verification after robustness guard: full `pytest` passed with `85 passed in 18.11s`; `compileall -q src tests` passed.

## 2026-05-09

- Started final architecture refactor for permission-aware capability catalog and action-level tool planning.
- Session catchup showed previous LLM tool planning work already landed locally.
- Read current permissions, registry, daily tools, prompts, nodes, contracts, and existing tests.
- Added red tests in `tests/test_permission_aware_capabilities.py`.
- Red run: `7 failed, 1 passed`; failures confirm missing role-filtered contracts, missing message_type/context_usage/selected_action state, and public prompt leaking calendar tool contracts.
- Implemented action-level permissions, role-filtered ToolRegistry contracts, planner state fields, selected_action execution checks, smalltalk/permission direct answers, and admin tools action metadata.
- Updated legacy tests to the final no-keyword-routing semantics.
- Full test run after implementation: `93 passed in 18.88s`.
- Updated README, ARCHITECTURE, SECURITY, and INTERVIEW_GUIDE for permission-aware catalog, action-level permissions, Planner schema, smalltalk handling, and event_type semantics.
- Final verification after removing test-generated calendar data: full `pytest` passed with `93 passed in 16.62s`; `compileall -q src tests` passed.
- Investigated trace `trace_d6182b1471c04bdc88cae367d53ff41c`: Planner selected `manage_company_calendar.query` with dates, but conflicting `route=direct` caused the graph to skip `call_tool`.
- Added red tests for this schema-contract conflict and smalltalk accidental tool leakage; red run failed as expected with 2 failures.
- Implemented Planner contract normalization in `understand_query`: allowed selected tools normalize to `route=tool`, while `smalltalk`/`permission_required`/`reject` clear tool fields.
- Target run after fix: `tests/test_permission_aware_capabilities.py` selected tests passed with `2 passed`; broader Planner/permission run passed with `19 passed`.
- Full verification: `TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest -q` passed with `95 passed in 17.04s`; `compileall -q src tests` passed.
- Investigated trace `trace_e0a5dd807a7f40ce9a46ed1e3fca9773`: Planner derived next-week dates from `previous_tool_context` and skipped `get_current_datetime`.
- Added red tests proving current relative-time questions must call datetime first and pure datetime direct plans normalize to `get_current_datetime`.
- Implemented current datetime middleware in `understand_query`: current-message relative time overrides planner/context dates and forces tool-side date resolution.
- Cleaned unused LLM route prompt/imports after route became a deterministic state-machine separator.
- Fixed role-policy consistency: API schema now accepts `public`; auth store preserves valid `tool.action` specs; frontend role editor can save action-level tool policies.
- Target verification: Planner/tool tests passed with `21 passed`; auth/permission/tool critical tests passed with `45 passed`.
- Full verification after all changes: `pytest -q` passed with `99 passed in 19.14s`; `compileall -q src tests` passed; `git diff --check` passed.
