# LangGraph Agentic RAG Refactor Plan

## Goal
Refactor the project into a safer, clearer enterprise Agentic RAG system with trustworthy evaluation, strong capability contracts, hard execution gates, slimmer LangGraph nodes, stable RAG behavior, and verified test/eval results.

## Current Phase
- [x] Initialize persistent planning files
- [x] Phase 1: Inspect requested files, tests, and eval fixtures
- [x] Phase 2: Establish baseline and write baseline report
- [x] Phase 3: Fix evaluator trustworthiness
- [x] Phase 4: Add capability contract layer and hard validation/resolution gates
- [x] Phase 5: Extract domain services and refactor answer composition
- [x] Phase 6: Verify unit tests, eval suites, and write final report
- [x] One-shot Milestone 1: fixed-now TimeContext and request-level cache
- [x] One-shot Milestone 2: CapabilityRegistry handler interface and graph catalog integration
- [x] One-shot Milestone 3: planning_contract.py compatibility facade
- [x] One-shot Milestone 4: graph/nodes.py compatibility boundary under 800 lines
- [x] One-shot Milestone 9: evaluator failure category attribution
- [ ] One-shot Milestone 10: final old2 cleanup, full tests, final evals, final report
- [x] 2026-05-19 Unified mainline closure fixes: TimeResolver, task-level validator, ReAct guards, calendar selector pre-call resolution
- [x] 2026-05-19 RAG regression fixes: smalltalk fallback, short Chinese evidence verifier, supporting-only answer evidence, RAG empty execution status
- [x] 2026-05-19 Smalltalk trace fix: empty direct/no-op plans validate as valid and preserve smalltalk intent
- [x] 2026-05-19 State/RAG/Eval enhancement: standardized state views, bounded RAG self-correction, failure classifier and auto reports

## Milestones
1. Baseline report written under `outputs/` or `docs/`.
2. Evaluator separates infra errors from agent failures and includes trajectory checks.
3. Calendar write safety gates prevent unsafe writes before real tools.
4. Domain capability modules own business rules; `nodes.py` is orchestration-focused.
5. Tool answers use structured `AnswerPacket` data, not raw state dumps.
6. Existing unit tests and requested eval suites are rerun after each relevant milestone.

## Constraints
- Do not hard-code keyword/case hacks to pass tests.
- Do not place new business rules in `graph/nodes.py`.
- Do not let LLM decide permissions, final date math, multi-candidate write selection, or tool schema repair.
- Do not pass symbolic dates or placeholder event IDs into real write tools.
- Do not count infrastructure failures as agent failures.
- Do not degrade RAG clean behavior while refactoring tool capabilities.

## Errors Encountered
| Time | Error | Root Cause | Resolution |
|---|---|---|---|
| 2026-05-17 | Unit baseline: 3 failures in planning latency contract | Planner prompt scoping/default-plan behavior is too broad | Pending planner/capability refactor |
| 2026-05-17 | RAG clean sample: 8/8 failed at latency 0 | RAG eval runner import error for missing prompt constants | Pending infra/evaluator fix |
| 2026-05-17 | Full V2 E2E final run: 20/64 reported failed at 0ms | DashScope free-tier quota exhausted after 44 executable cases | Evaluator now marks them as infra_error; executed Agent cases were 44/44 |
| 2026-05-18 | Round10 aligned12: 3/12 failed | Fixture/date expectation drift and overly strict must-contain checks; no unsafe writes observed | Recorded as evaluator/fixture issues for next round, not patched case-by-case |
| 2026-05-18 | One-shot red tests initially failed for TimeContext, registry handlers, planning facade, nodes boundary, tool-input ownership, eval categories | Requested architecture gaps were still present | Implemented shared services/shims and reran focused suite: 34 passed |
## 2026-05-18 Unified Mainline Status

- [x] 图主线收口到 TimeContext -> Planner -> TimeResolver -> ReActExecutor -> AnswerLLM -> Memory。
- [x] 统一 TimeResolver，移除 active source 中的 canonical relative 旧链路。
- [x] ReActExecutor 成为唯一执行器，并保留权限、schema、selector、event_id 安全门禁。
- [x] AnswerService 统一走 LLM，并使用 AnswerPacket/locked facts 防止日期、工具结果、RAG citation 幻觉。
- [x] RAG answerability gate 与 rerank 默认关闭/fallback 生效。
- [x] 旧测试、旧 facade、旧 eval 输出移动到 `old2/unified_mainline_legacy_20260518/`。
- [x] `compileall` / `pytest tests -q` / aligned12 / mixed smoke / RAG sample8 验证完成。
- [ ] V2 first20 待外部模型 quota 恢复后重跑。
- [ ] RAG clean32 待更长运行窗口或缓存预热后重跑完整集。

## 2026-05-19 Closure Fix Checklist

- [x] TimeResolver supports bare weekday aliases, `前天`, `大后天`, `下下周`, and `下下月` without substring duplicate hits.
- [x] Create-context bare weekday with a past same-day time rolls to the next week.
- [x] `validate_plan` is task-level and preserves executable tasks when later tasks need clarification.
- [x] ReActExecutor blocks premature finish, enforces `depends_on`, and returns success when the fifth step completes all work.
- [x] Calendar update/delete selectors are resolved from previous context or latest observations before real write tool calls.
- [x] `react_execute` completion assessment no longer marks `need_clarification/blocked/failed/error` as ready.
- [x] Compileall, focused tests, and full pytest verified in the Ubuntu `ollama` environment.

## 2026-05-19 RAG Regression Checklist

- [x] Explicit `smalltalk/direct/datetime` empty plans do not create RAG tasks.
- [x] Empty RAG fallback remains only for explicit RAG intent/requirement, including legacy `route=rag`.
- [x] Short Chinese policy queries such as `公司报销制度` accept clearly matching finance supporting sources.
- [x] Candidate sources remain trace/debug-only and do not enter AnswerPacket or final answer prompt when supporting sources are empty.
- [x] Mixed tool success plus RAG empty/no_evidence is represented as `partial`; pure empty RAG is `insufficient_evidence`.
- [x] Compileall, focused RAG/answer tests, legacy RAG-path context test, and full pytest verified.

## 2026-05-19 Smalltalk Trace Checklist

- [x] Read trace `agent_trace_20260519_010808_trace_d75650cd80ab405388cdf7ba5132833d.json` and identified failing layer as validator, not planner/RAG/answer prompt.
- [x] Added regression that checks `smalltalk + tasks=[]` stays `valid` after `validate_plan`.
- [x] Fixed empty direct/no-op plan validation without adding smalltalk keyword patches.
- [x] Verified compileall, focused suite, and full pytest.

## 2026-05-19 State/RAG/Eval Enhancement Checklist

- [x] Added standardized state views: `runtime_context`, `plan_state`, `execution_state`, `answer_state`.
- [x] Added `state_views.py` helpers and synchronized legacy top-level facade fields from standardized regions.
- [x] Added bounded RAG self-correction with LLM-only `retrieval_query`, same-topic validation, target KB subset checks, and max one retry per RAG task.
- [x] Kept candidate evidence out of AnswerPacket/prompt; supporting evidence remains the only answer-facing RAG evidence.
- [x] Added eval failure classifier with planning/time/tool/rag/answer/safety/infra/evaluator taxonomy.
- [x] Added auto markdown eval/run report helpers and integrated auto eval report generation into both eval scripts.
- [x] Fixed generic answer synthesis overreach that appended “无权执行” to safety explanations without permission events.
- [x] Fixed query tool input canonicalization so symbolic `date` is removed after `start_date/end_date` are resolved.
- [x] Verified compileall, focused tests, full pytest, aligned12, mixed smoke, and RAG clean sample8.
