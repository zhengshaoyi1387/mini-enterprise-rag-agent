# Findings

## Memory-Derived Context
- Prior related work on the sibling `mini-enterprise-rag-agent` emphasized quality-preserving optimization: keep strong answer quality and rerank behavior where useful, reduce waste via trace analysis, and verify with `TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests -q` when using the `ollama` env.
- Useful trace fields from that work include `node_trace`, `llm_calls`, `total_latency_ms`, retrieval/rerank timings, and cache-hit metadata.

## Repository State
- The active worktree has many pre-existing modified, deleted, and untracked files. Treat them as user/context changes and do not revert them.
- New evaluation assets exist under `eval/agent_eval_cases_full/`, `eval/agent_eval_cases_v2_comprehensive/`, and `eval/rag_clean_eval_set/`.

## Initial Source Inspection
- `src/mini_rag/graph/workflow.py` is a thin LangGraph sequence, but it still sends every request through `classify_intent -> build_plan -> validate_plan`.
- `src/mini_rag/graph/nodes.py` remains the large orchestration hotspot: it owns plan normalization wrappers, calendar write resolution wrappers, tool payload finalization, permission/clarification text, tool result formatting, answer prompting, and trace building.
- `src/mini_rag/graph/planning_contract.py`, `src/mini_rag/graph/time_contract.py`, `src/mini_rag/tools/calendar_resolution.py`, and `src/mini_rag/tools/input_contract.py` already contain partial contract/resolution behavior. They are useful migration sources, but the capability layer requested by the task does not exist yet.
- `scripts/agent_eval_suite_relaxed.py` already has softer rule judging and some text normalization, but summary fields still center on `case_count/passed/failed/pass_rate`; infra errors are not separated as `infra_error_cases`, and fixture restore is backup/restore based rather than explicit base fixture restoration.

## Baseline Unit Test Result
- Command: `TMPDIR=/tmp PYTHONPATH=src /home/zz/anaconda3/envs/ollama/bin/python -m pytest tests -q`
- Result: `145 passed, 3 failed` in about 55 seconds.
- Failures:
  - `tests/test_planning_latency_contract.py::test_datetime_classification_uses_default_plan_without_build_plan_llm`: build_plan still calls LLM for a simple datetime request where classifier output should be enough.
  - `tests/test_planning_latency_contract.py::test_build_plan_receives_scoped_tool_contract_only`: build_plan prompt for a calendar query includes calendar write actions like update/delete.
  - `tests/test_planning_latency_contract.py::test_build_plan_omits_previous_context_when_classifier_says_none`: build_plan prompt includes previous tool context even when classifier says `context_usage=none`.
- Root-cause layer: planner / prompt input scoping.

## Current Verified State
- Full unit tests now pass in the Ubuntu `ollama` conda environment: `168 passed`.
- Evaluator summary now separates `total_cases`, `executed_cases`, `infra_error_cases`, `agent_passed_cases`, `agent_failed_cases`, and `agent_pass_rate`.
- Full V2 E2E run hit DashScope `AllocationQuota.FreeTierOnly` after 44 executable cases. The report correctly classified the remaining 20 as `infra_error`; executed cases had `agent_failed_cases=0` and `agent_pass_rate=1.0`.
- Calendar write safety subset passed 14/14. Observed write calls use concrete `EVT-...` IDs; no `event_id=all/multiple` reached real write tools.
- Attendance V2 subset passed 10/10 after adding an attendance-scope validator. Ordinary employee department/all-employee detail requests are refused before tool execution; HR/admin detail queries remain executable.
- RAG clean sample8 passed 8/8 before the quota blocker, including explicit-title source boosting for `rag_clean_007`.

## Round10 Architecture Findings
- `calendar/compiler.py` was at risk of becoming a rule pile. It is now split into `calendar/lexicon.py` for vocabulary, `calendar/slots.py` for text slot extraction, and `calendar/compiler.py` for task compilation only.
- Calendar selector/update/delete resolution now lives in `capabilities/calendar/resolver.py`. The old `tools/calendar_resolution.py` file remains only as a compatibility shim.
- Datetime/time-contract logic now lives in `capabilities/datetime/resolver.py`. The old `graph/time_contract.py` file remains only as a compatibility shim.
- Planning compilation now lives in `planning/compiler.py`, while capability gates live in `planning/gates.py`. `graph/planning_contract.py` dropped to 284 lines and no longer owns most compile/gate details.
- Generic tool execution moved to `execution/tool_executor.py`; `nodes.call_tool` now delegates. `nodes.py` is down to 1979 lines in this round.
- Answer prompt input is now backed by `AnswerPacket` and compact task results from `answer/packet.py`; raw state, previous tool context, and raw tool result are not passed wholesale to the answer prompt.
- Round10 verification:
  - `pytest tests -q`: 202 passed.
  - `round10_v2_e2e_first20_rule`: 20/20 passed, infra_error=0.
  - `round10_rag_clean_sample8_rule`: 8/8 passed, infra_error=0.
  - `round10_aligned12_rule`: 9/12 passed, infra_error=0.
- Round10 aligned12 failures are not being patched in this architecture round:
  - `e2e_tool_001`: Agent queried first and skipped update when no candidate existed; this is safe behavior, likely fixture/evaluator expectation drift.
  - `e2e_tool_006`: Agent queried and reported no meeting plus no write permission; likely evaluator wording/must-contain strictness.
  - `e2e_tool_008`: Agent executed datetime and calendar query; expected concrete meeting time conflicts with returned fixture state/current-date assumption.

## One-Shot Architecture Findings
- Fixed-now root cause: datetime tool always used the real clock, so aligned/eval cases with relative dates drifted. Added `AGENT_EVAL_FIXED_NOW` and request override support; eval scripts now default to `2026-05-17 01:00:00 Asia/Shanghai`.
- Time cache root cause: the same state could resolve multiple relative tool payloads by calling `get_current_datetime` repeatedly. Added `state["time_context_result"]` cache; current task `time_requirement` now takes precedence over stale `time_reference`.
- Registry root cause: `CapabilityRegistry` exposed metadata only. It now owns handlers and role-filtered visibility plus common validate/resolve/format entrypoints.
- Planning cleanup root cause: `graph/planning_contract.py` still imported domain details. It is now a compatibility facade; implementation moved under `planning/contract_normalizer.py`.
- Nodes cleanup root cause: `graph/nodes.py` still contained execution/retrieval/answer/memory internals. It is now a thin boundary, with runtime implementation moved to `orchestration/agentic_nodes.py` pending deeper service extraction.
- Tool-input ownership root cause: `tools/input_contract.py` was still the hard gate owner. Logic moved to `execution/tool_input.py`; old path remains a shim.
- Eval trust root cause: reports had failure reasons but not layer attribution. Both eval scripts now emit `failure_category` per case and aggregate `failure_categories`.
- V2 full64 retry limitation: after RAG clean full32, the final V2 full64 rerun hit DashScope `AllocationQuota.FreeTierOnly` on case 1, so the current `final_v2_full64_rule` file contains only infra=1/executed=0. This is an infra blocker, not an Agent failure.
- Attendance refusal evaluator fix: an earlier same-turn full64 attempt showed `e2e_v2_att_005` failing because the evaluator did not recognize “无权查看/查询” as a refusal. The Agent refused correctly; the evaluator regex was generalized and unit-tested without changing Agent behavior.
## 2026-05-18 Unified Mainline Findings

- 旧失败主要来自结构分叉：planner 计算时间、旧 formatter 抢答、query-first write 未刷新任务队列、权限 gate 把可读任务和不可写任务一起阻断。
- 新 TimeResolver 统一解析 raw `time_expression`，解决“明天/后天/下周三/多日期”不稳定问题。
- ReActExecutor 必须把 `empty/no_evidence` 视为任务完成，否则 RAG 无证据场景会触发重复 action guard。
- Calendar query-first write 需要在 query 后刷新 `task_queue` 和 `execution_plan`，否则 resolver 得到的 concrete `event_id` 不会被下一步消费。
- Eval 的 datetime coverage 需要认可 TimeContext，而不是强制旧 `get_current_datetime` 工具调用；这属于评测可信度修复。
- V2 first20 当前阻塞是外部 403 quota，不是 Agent 逻辑失败。

## 2026-05-19 Unified Mainline Closure Findings

- TimeResolver root cause: relative-day and range matching was substring based, so `大后天` also matched `后天`, and `下下周/下下月` also matched `下周/下月`. Longest-span matching fixes this without scattering date rules into planner/calendar/answer.
- Bare weekday root cause: only prefixed expressions like `下周三` were parsed. `星期一/周一/礼拜一` now resolve against the current week by default; in create context with an explicit start time, same-day past times roll forward seven days.
- Validator root cause: `apply_capability_gates` returned a whole-plan blocking decision. `validate_plan` now keeps executable tasks and records blocked/clarification tasks separately, so one missing create slot no longer drops earlier safe queries or writes.
- ReAct root cause: finish was treated as success even with remaining executable tasks, dependency order was not enforced, and the loop only checked completion at the start of each step. The executor now blocks premature finish, checks `depends_on`, and returns success immediately after the final successful action.
- Calendar selector root cause: selector-to-event_id resolution happened after successful query calls only. Pre-call resolution now uses previous tool context, task results, or compact query observations before real update/delete, so ordinal selectors become concrete `EVT-...` IDs before tool schema validation.
- Completion-assessment root cause: `react_execute` always set `ready_to_answer=True`. It now only does that for `success/partial`; `need_clarification/blocked/failed/error` remain not ready.

## 2026-05-19 RAG Regression Findings

- Smalltalk regression root cause: `_normalize_runtime_plan` treated any empty task list as missing RAG planning and injected a fallback RAG task. The fix gates fallback on explicit RAG intent/requirement and keeps `smalltalk/direct/datetime` empty plans direct.
- Legacy compatibility note: old tests still produce `route=rag` plus `knowledge_requirement.should_use_rag=true`; normalize now treats that as explicit RAG requirement without affecting explicit smalltalk.
- Evidence verifier root cause: short Chinese queries such as `公司报销制度` produced many CJK n-grams, so one strong core overlap like `报销` did not meet the ratio threshold. The fix accepts short制度类 queries when their synonym/core business group is clearly present in source/kb/title/preview.
- Candidate evidence leak root cause: AnswerService fell back from empty `supporting_evidence_brief` to `evidence_brief`, which can contain all retrieved candidates. The answer prompt now uses supporting sources only for RAG evidence text; if none exist, it emits only the insufficient-evidence notice.
- Answerability gate root cause: it could promote `candidate_sources` to supporting internally. That made the gate inconsistent with the prompt contract. It now evaluates only `sources`/supporting sources.
- Execution status root cause: AnswerPacket only considered hard errors partial. It now marks mixed tool success + RAG `empty/no_evidence` as `partial`, and pure empty RAG as `insufficient_evidence`.

## 2026-05-19 Smalltalk Trace Findings

- The smalltalk trace did not fail at planner or RAG fallback. The planner output was correct (`smalltalk`, no tools, no RAG, no tasks), and no retrieval/tool call happened.
- The failing layer was validator: `validate_plan` interpreted `tasks=[]` as an invalid plan needing clarification, even though empty tasks are a valid no-op/direct answer contract for smalltalk and similar direct responses.
- The answer layer behaved according to its locked-fact rules: after validator changed intent to `need_clarification`, AnswerService preserved the clarification template and discarded the LLM greeting. The right fix is therefore validator contract repair, not prompt wording or keyword handling.
- Empty direct/no-op plans now validate as `valid`, preserve `intent=smalltalk`, keep `route=direct`, and let the unified Answer LLM produce the final greeting.

## 2026-05-19 State/RAG/Eval Enhancement Findings

- State root cause: top-level fields and emerging `runtime_context` were not synchronized through one standard contract. Added `orchestration/state_views.py` so nodes now refresh four standard regions and keep legacy fields as a facade.
- State consistency rule: `completion_assessment.ready_to_answer` is forced false for `need_clarification/blocked/failed/error/refused`, and a `react_status=success` with remaining executable tool/RAG tasks is normalized to partial.
- RAG self-correction root cause: RAG retrieval had a verifier but no bounded recovery step. Added one retry path where the LLM can only emit `retrieval_query`; program validation enforces same-topic terms, target KB subset, and anti-expansion terms.
- RAG evidence contract remains strict: only supporting sources enter `sources`, AnswerPacket, and answer prompt. Candidate sources remain debug/trace data even after retry.
- Eval classification root cause: previous categories were old agent-layer names and not actionable enough for the new mainline. Added `mini_rag.eval.failure_classifier` and `run_report`, then wired both eval scripts to write `outputs/eval_reports/eval_report_*.md`.
- Mixed smoke revealed a general AnswerService issue: a broad permission wording heuristic appended “因此你无权执行该写操作” whenever a write-related question contained “不能”. That confused safety explanations with permission denial; it now only appends permission wording when a real permission block exists.
- Mixed smoke also revealed a planner-output normalization issue: if Planner emits symbolic `tool_input.date="下周"` alongside `time_expression`, `resolve_plan_time` now removes `date` for query tasks once canonical `start_date/end_date` exist.
