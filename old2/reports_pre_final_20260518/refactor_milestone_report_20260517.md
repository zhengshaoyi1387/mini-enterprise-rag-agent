# LangGraph Agentic RAG Refactor Milestone Report

## Scope

This milestone focused on evaluator trustworthiness, capability contracts, hard execution gates, calendar/attendance safety, RAG stability, and regression verification.

## Architecture Changes

- Added strong shared contract models in `src/mini_rag/core/contracts.py`.
- Added capability contract packages under `src/mini_rag/capabilities/` for datetime, calendar, attendance, RAG, and aggregate contract loading.
- Moved calendar validation/resolution/compiler behavior into capability/tool-domain modules:
  - `src/mini_rag/capabilities/calendar/validator.py`
  - `src/mini_rag/capabilities/calendar/compiler.py`
  - `src/mini_rag/tools/calendar_resolution.py`
- Added attendance scope validation in `src/mini_rag/capabilities/attendance/validator.py`.
- Tightened `src/mini_rag/graph/planning_contract.py` so planner output is normalized and validated before executable tools see it.
- Scoped planner tool contracts in `src/mini_rag/tools/registry.py` to reduce accidental action space.
- Preserved terminal tool-error template answers in `src/mini_rag/graph/nodes.py` instead of re-planning or overwriting them with answer LLM output.
- Added explicit-title RAG source boosting in `src/mini_rag/retrieval/retriever.py`.

## Evaluation Trustworthiness

- `scripts/agent_eval_suite.py` and `scripts/agent_eval_suite_relaxed.py` now report:
  - `total_cases`
  - `executed_cases`
  - `infra_error_cases`
  - `agent_passed_cases`
  - `agent_failed_cases`
  - `agent_pass_rate`
- Infra errors such as 403/quota/network/import errors are excluded from Agent failure counts.
- Calendar and attendance fixtures are restored before isolated tool/e2e cases unless a case explicitly asks for continuous state.
- Rule judge supports trajectory fields including expected tool/action, forbidden actions, write/refusal expectations, and expected status.
- Text normalization handles Chinese/ISO dates, time dashes, weekday aliases, empty-result wording, and meeting-room spacing.

## Verification Results

| Command | Result |
|---|---|
| `TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests -q` | 168 passed |
| `scripts/agent_eval_suite_relaxed.py --suite e2e --questions eval/agent_eval_cases_full/agent_e2e_eval_cases_aligned.jsonl --judge rule --mode hybrid --output outputs/eval/round9_aligned12_rule` | 12/12 passed, 0 infra |
| `scripts/agent_eval_suite_relaxed.py --suite e2e --questions eval/agent_eval_cases_v2_comprehensive/eval/agent_e2e_comprehensive_v2.jsonl --limit 20 --judge rule --mode hybrid --output outputs/eval/round9_v2_e2e_first20_rule` | 20/20 passed, 0 infra |
| `scripts/agent_eval_suite_relaxed.py --suite e2e --questions <calendar update/delete subset> --judge rule --mode hybrid --output outputs/eval/round9_v2_calendar_write_safety_rule` | 14/14 passed, 0 infra |
| `scripts/agent_eval_suite_relaxed.py --suite e2e --questions <attendance subset> --judge rule --mode hybrid --output outputs/eval/round10_v2_attendance_rule` | 10/10 passed, 0 infra |
| `scripts/agent_eval_suite_relaxed.py --suite rag --questions eval/rag_clean_eval_set/rag_clean_questions.jsonl --limit 8 --judge rule --mode hybrid --output outputs/eval/round9_rag_clean_sample8_rule` | 8/8 passed, 0 infra |
| `scripts/agent_eval_suite_relaxed.py --suite e2e --questions eval/agent_eval_cases_v2_comprehensive/eval/agent_e2e_comprehensive_v2.jsonl --judge rule --mode hybrid --output outputs/eval/round10_v2_e2e_full64_rule` | total 64, executed 44, infra 20, agent passed 44, agent failed 0, agent pass rate 1.0 |

## Remaining Gaps

- Full V2 execution was blocked by DashScope `AllocationQuota.FreeTierOnly` after 44 executable cases. The evaluator classified this correctly as infra.
- `nodes.py` is safer, but still not fully reduced to pure LangGraph orchestration. More answer formatting and domain service extraction remains for the next milestone.
- Full RAG clean 32-case eval was not rerun after quota exhaustion; sample8 passed before the blocker.

## Acceptance Status

Partially satisfied with an infrastructure blocker:

- Unit tests: satisfied.
- aligned 12: satisfied.
- V2 executable cases: satisfied for executed cases; infra separated correctly.
- Calendar write safety: satisfied on the dedicated V2 write subset.
- Attendance query stability: satisfied on V2 attendance subset.
- RAG clean: sample passed; full rerun blocked by quota.
- Full `nodes.py` slimming/domain extraction: partially complete, not fully complete.
