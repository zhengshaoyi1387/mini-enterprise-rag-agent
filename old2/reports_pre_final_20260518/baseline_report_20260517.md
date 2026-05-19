# Baseline Report - 2026-05-17

## Environment
- Python: `/home/zz/anaconda3/envs/ollama/bin/python`
- Command prefix: `TMPDIR=/tmp PYTHONPATH=src`
- Policy note: after the initial baseline, iterative verification will use focused tests/eval subsets; full regression is reserved for the final milestone.

## Unit Tests
- Command: `TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests -q`
- Result: `145 passed, 3 failed`

| Failure | Layer | Root Cause |
|---|---|---|
| `tests/test_planning_latency_contract.py::test_datetime_classification_uses_default_plan_without_build_plan_llm` | planner | Simple datetime classifier output still goes through build_plan LLM instead of using a default executable plan. |
| `tests/test_planning_latency_contract.py::test_build_plan_receives_scoped_tool_contract_only` | planner | Calendar query planning prompt still exposes write actions (`update/delete`) instead of a scoped query contract. |
| `tests/test_planning_latency_contract.py::test_build_plan_omits_previous_context_when_classifier_says_none` | planner | Previous tool context is passed into build_plan even when classifier says `context_usage=none`. |

## Eval Baseline

| Suite | Command | Result | Report |
|---|---|---:|---|
| aligned E2E 12 | `scripts/agent_eval_suite_relaxed.py --suite e2e --judge rule --mode hybrid --questions eval/agent_eval_cases_full/agent_e2e_eval_cases_aligned.jsonl` | 9/12 passed | `outputs/eval/baseline_aligned12_rule.md` |
| V2 E2E first 20 | `scripts/agent_eval_suite_relaxed.py --suite e2e --judge rule --mode hybrid --questions eval/agent_eval_cases_v2_comprehensive/eval/agent_e2e_comprehensive_v2.jsonl --limit 20` | 18/20 passed | `outputs/eval/baseline_v2_e2e_first20_rule.md` |
| RAG clean sample 8 | `scripts/agent_eval_suite_relaxed.py --suite rag --judge rule --mode hybrid --questions eval/rag_clean_eval_set/rag_clean_questions.jsonl --limit 8` | 0/8 executed successfully | `outputs/eval/baseline_rag_clean_sample8_rule.md` |

## Failure Attribution

| Case | Layer | Root Cause |
|---|---|---|
| `e2e_tool_004` | planner / evaluator | Planner generated `2024-05-01..2024-05-31` for “本月” in the second attendance task despite the run date being 2026; evaluator also treats answer text containing “无法” as a refusal even when the request should not be refused. |
| `e2e_tool_008` | planner | Multi-objective datetime + calendar query was planned as only `get_current_datetime`; the calendar query was never executed. |
| `e2e_tool_010` | validator / time contract | The second task explicitly had `2026-05-12`, but normalization inherited the root `last_week` relative time and executed the wrong date range. |
| `e2e_v2_cal_query_008` | validator / time contract | Symbolic date placeholders `${tomorrow}` and `${day_after_tomorrow}` reached the real calendar tool, causing `invalid date format`. |
| `e2e_v2_cal_create_003` | validator | Missing date/time create request called the real calendar create path and failed schema validation; it should have become `needs_clarification` with no write call. |
| `rag_clean_001..008` | infra / evaluator | RAG runner failed before execution: `cannot import name 'AGENT_SYSTEM_PROMPT' from 'mini_rag.prompts'`. These are not Agent logic failures and should be separated as infra errors by the evaluator. |

## Baseline Conclusions
- The highest-risk correctness issues are at the planner/validator boundary: date inheritance, symbolic date leakage, missing-slot create execution, and insufficient multi-task planning.
- Evaluator trustworthiness is not yet adequate: infra errors are counted as failed cases, and broad refusal markers can mislabel normal caveated answers as refusals.
- `nodes.py` still holds answer formatting, LLM-based tool input repair, and domain-specific guard behavior; these must move behind capability/domain contracts before deeper optimization.

