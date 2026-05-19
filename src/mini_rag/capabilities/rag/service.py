from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from mini_rag.capabilities.rag.compiler import normalize_query_key
from mini_rag.capabilities.rag.evidence_judge import judge_rag_evidence_with_llm, select_sources_by_ids
from mini_rag.capabilities.rag.formatter import (
    build_evidence_summary_from_sources,
    dedupe_sources,
    dedupe_task_results,
    public_search_task,
    sources_to_evidence_text,
)
from mini_rag.capabilities.rag.self_correct import maybe_rewrite_rag_query
from mini_rag.config import Settings
from mini_rag.graph.utils import compact_evidence_text, dedupe_keep_order, document_key, document_to_source
from mini_rag.security.permissions import assert_tool_permission, normalize_role


class RAGRetrievalService:
    """Plan and execute RAG retrieval tasks outside LangGraph node code.

    Outer ReAct selects the RAG task. This service owns the inner RAG loop:
    retrieve -> LLM evidence judge -> same-topic retrieval rewrite -> retry -> judge.
    Multiple independent RAG tasks may be submitted in one call. Each task is
    processed in isolation and merged back in plan order, so one unsupported task
    cannot contaminate another task's evidence judgment or retry query.
    """

    def __init__(
        self,
        settings: Settings,
        get_retriever: Callable[[], Any],
        get_role_policies: Callable[[dict[str, Any]], Any],
        *,
        llm: Any | None = None,
        judge_llm: Any | None = None,
        reflect_llm: Any | None = None,
    ) -> None:
        self.settings = settings
        self._get_retriever = get_retriever
        self._get_role_policies = get_role_policies
        self.llm = llm
        self.judge_llm = judge_llm or llm
        self.reflect_llm = reflect_llm or llm

    def _model_name(self, purpose: str) -> str:
        if purpose == "judge":
            value = getattr(self.settings, "rag_judge_model", None)
        elif purpose == "reflect":
            value = getattr(self.settings, "rag_reflect_model", None)
        else:
            value = None
        return str(
            value
            or getattr(self.settings, "qwen_control_model", None)
            or getattr(self.settings, "qwen_chat_model", "control_llm")
            or "control_llm"
        )

    def retrieve(self, state: dict[str, Any]) -> dict[str, Any]:
        service_started = time.perf_counter()
        role = normalize_role(state.get("role"))
        assert_tool_permission(role, "search_knowledge_base", role_policies=self._get_role_policies(state))
        state.setdefault("observations", []).append(
            {
                "type": "permission_check",
                "scope": "tool",
                "tool_name": "search_knowledge_base",
                "role": role,
                "allowed": True,
            }
        )

        pending = [dict(task) for task in (state.get("pending_search_tasks") or []) if isinstance(task, dict)]
        if not pending:
            state.setdefault("observations", []).append({"type": "retrieve", "message": "没有待检索任务，跳过。"})
            return state

        retriever = self._get_retriever()
        all_docs = list(state.get("retrieved_docs") or [])
        executed_queries = list(state.get("executed_queries") or [])
        executed_query_keys = list(state.get("_executed_query_keys") or [])
        retrieval_cache = state.setdefault("_retrieval_cache", {})
        cache_enabled = bool(getattr(self.settings, "agent_enable_retrieval_cache", True))
        observations = state.setdefault("observations", [])
        tool_calls = state.setdefault("tool_calls", [])

        runnable: list[dict[str, Any]] = []
        cached_by_key: dict[str, tuple[list[Any], dict[str, Any]]] = {}
        existing_keys = {str(item) for item in executed_query_keys}

        for task in pending:
            query = str(task.get("query") or "").strip()
            if not query:
                continue
            key = normalize_query_key(query)
            if not key:
                continue
            if cache_enabled and key in retrieval_cache:
                cached = retrieval_cache[key]
                docs = list(cached.get("docs") or [])
                trace = dict(cached.get("trace") or {})
                trace["retrieval_cache_hit"] = True
                trace.setdefault("retrieval_wall_ms", 0.0)
                if trace.get("rerank_enabled"):
                    trace["rerank_cache_hit"] = True
                cached_by_key[key] = (docs, trace)
            elif key not in existing_keys:
                runnable.append(task)
            existing_keys.add(key)

        def run_retrieval(task: dict[str, Any]) -> tuple[dict[str, Any], list[Any], dict[str, Any]]:
            query = str(task.get("query") or "").strip()
            top_k = int(task.get("top_k") or self.settings.top_k)
            candidate_k = int(task.get("candidate_k") or self.settings.candidate_k)
            enable_rerank = task.get("enable_rerank", state.get("enable_rerank"))
            started = time.perf_counter()
            try:
                docs, trace = retriever.search(
                    query,
                    top_k=top_k,
                    candidate_k=candidate_k,
                    retrieval_mode=state.get("retrieval_mode"),
                    enable_rerank=enable_rerank,
                    kb_ids=task.get("target_kbs") or state.get("used_kbs", []),
                )
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                try:
                    docs, trace = retriever.search(
                        query,
                        retrieval_mode=state.get("retrieval_mode"),
                        enable_rerank=enable_rerank,
                        kb_ids=task.get("target_kbs") or state.get("used_kbs", []),
                    )
                except TypeError as second_exc:
                    if "unexpected keyword argument" not in str(second_exc):
                        raise
                    docs, trace = retriever.search(
                        query,
                        retrieval_mode=state.get("retrieval_mode"),
                        enable_rerank=enable_rerank,
                    )
            trace = dict(trace or {})
            trace.setdefault("retrieval_cache_hit", False)
            trace.setdefault("rerank_cache_hit", False)
            trace.setdefault("retrieval_wall_ms", round((time.perf_counter() - started) * 1000, 2))
            return task, list(docs or []), trace

        initial_results: list[tuple[dict[str, Any], list[Any], dict[str, Any]]] = []
        max_retrieval_workers = max(1, int(getattr(self.settings, "agent_retrieval_workers", 1) or 1))
        if len(runnable) > 1 and max_retrieval_workers > 1:
            with ThreadPoolExecutor(max_workers=min(max_retrieval_workers, len(runnable))) as pool:
                futures = [pool.submit(run_retrieval, task) for task in runnable]
                for future in as_completed(futures):
                    initial_results.append(future.result())
        else:
            for task in runnable:
                initial_results.append(run_retrieval(task))

        by_key: dict[str, tuple[dict[str, Any], list[Any], dict[str, Any]]] = {}
        for task, docs, trace in initial_results:
            by_key[normalize_query_key(str(task.get("query") or ""))] = (task, docs, trace)
        for task in pending:
            query = str(task.get("query") or "").strip()
            key = normalize_query_key(query)
            if key in cached_by_key:
                docs, trace = cached_by_key[key]
                by_key[key] = (task, docs, trace)

        def process_task(task: dict[str, Any]) -> dict[str, Any] | None:
            query = str(task.get("query") or "").strip()
            key = normalize_query_key(query)
            if not query or key not in by_key:
                return None
            _, docs, trace = by_key[key]

            task_id = str(task.get("task_id") or "").strip() or f"rag_{len(state.get('task_results') or []) + 1}"
            objective = str(task.get("objective") or query)
            original_question = str(state.get("question") or query)
            allowed_kbs = [str(kb) for kb in (state.get("used_kbs") or [])]

            local_trace_state: dict[str, Any] = {"llm_calls": []}
            local_observations: list[dict[str, Any]] = []
            local_tool_calls: list[dict[str, Any]] = []
            local_docs: list[Any] = []
            local_executed_queries: list[str] = []
            local_executed_keys: list[str] = []
            local_cache_updates: dict[str, dict[str, Any]] = {}
            query_runs: list[dict[str, Any]] = []
            evidence_judgments: list[dict[str, Any]] = []
            retry_decision: dict[str, Any] | None = None
            related_sources: list[dict[str, Any]] = []

            latency_trace: dict[str, Any] = {
                "next_action_ms": round(float(task.get("next_action_ms") or 0), 2),
                "skipped_next_action": bool(task.get("skipped_next_action")),
                "retrieve_1_ms": round(float(trace.get("retrieval_latency_ms", trace.get("retrieval_wall_ms", 0)) or 0), 2),
                "evidence_judge_1_ms": 0.0,
                "rag_reflect_ms": 0.0,
                "retrieve_2_ms": 0.0,
                "evidence_judge_2_ms": 0.0,
                "selected_sources_count": 0,
                "candidate_sources_count": 0,
                "supporting_sources_count": 0,
                "related_sources_count": 0,
                "triggered_reflect": False,
                "retry_executed": False,
                "skip_retry_reason": "",
            }

            srcs = [document_to_source(doc) for doc in docs]
            query_runs.append({"query": query, "docs": docs, "trace": trace, "sources": srcs})
            all_run_sources = list(srcs)
            local_docs.extend(docs)
            local_executed_queries.append(query)
            if key:
                local_executed_keys.append(key)
            if cache_enabled and key:
                local_cache_updates[key] = {"docs": list(docs), "trace": dict(trace)}

            judge_started = time.perf_counter()
            judge = judge_rag_evidence_with_llm(
                original_question=original_question,
                rag_task_objective=objective,
                candidate_sources=all_run_sources,
                llm=self.judge_llm,
                attempt=1,
                trace_state=local_trace_state,
                model_name=self._model_name("judge"),
                current_task_id=task_id,
                task_question=query,
            )
            latency_trace["evidence_judge_1_ms"] = round((time.perf_counter() - judge_started) * 1000, 2)
            evidence_judgments.append({"attempt": 1, **judge.to_dict()})
            local_observations.append({"type": "rag_evidence_judge", "task_id": task_id, "attempt": 1, **judge.to_dict()})
            supporting = select_sources_by_ids(all_run_sources, judge.supporting_source_ids) if judge.answerable else []
            related_sources = select_sources_by_ids(all_run_sources, judge.related_source_ids) if not judge.answerable else []

            if not judge.answerable or judge.sufficiency == "low":
                reflect_started = time.perf_counter()
                decision = maybe_rewrite_rag_query(
                    question=original_question,
                    task=task,
                    initial_query=query,
                    candidate_sources=all_run_sources,
                    unsupported_reason=judge.reason or "候选证据不足以回答当前子任务",
                    missing_evidence=list(judge.missing_evidence),
                    allowed_kbs=allowed_kbs,
                    llm=self.reflect_llm,
                    trace_state=local_trace_state,
                    model_name=self._model_name("reflect"),
                )
                latency_trace["rag_reflect_ms"] = round((time.perf_counter() - reflect_started) * 1000, 2)
                latency_trace["triggered_reflect"] = True
                retry_decision = decision.to_dict()
                retry_query = str(decision.retrieval_query or "").strip()
                retry_key = normalize_query_key(retry_query)
                if decision.should_retry and retry_query and retry_key and retry_key != key:
                    latency_trace["retry_executed"] = True
                    retry_task = dict(task)
                    retry_task["query"] = retry_query
                    retry_task["target_kbs"] = list(decision.target_kbs)
                    _, retry_docs, retry_trace = run_retrieval(retry_task)
                    latency_trace["retrieve_2_ms"] = round(float(retry_trace.get("retrieval_latency_ms", retry_trace.get("retrieval_wall_ms", 0)) or 0), 2)
                    retry_srcs = [document_to_source(doc) for doc in retry_docs]
                    query_runs.append({"query": retry_query, "docs": retry_docs, "trace": retry_trace, "sources": retry_srcs})
                    all_run_sources.extend(retry_srcs)
                    local_docs.extend(retry_docs)
                    local_executed_queries.append(retry_query)
                    local_executed_keys.append(retry_key)
                    if cache_enabled:
                        local_cache_updates[retry_key] = {"docs": list(retry_docs), "trace": dict(retry_trace)}

                    retry_judge_started = time.perf_counter()
                    retry_judge = judge_rag_evidence_with_llm(
                        original_question=original_question,
                        rag_task_objective=objective,
                        candidate_sources=all_run_sources,
                        llm=self.judge_llm,
                        attempt=2,
                        trace_state=local_trace_state,
                        model_name=self._model_name("judge"),
                        current_task_id=task_id,
                        task_question=query,
                    )
                    latency_trace["evidence_judge_2_ms"] = round((time.perf_counter() - retry_judge_started) * 1000, 2)
                    evidence_judgments.append({"attempt": 2, **retry_judge.to_dict()})
                    local_observations.append({"type": "rag_evidence_judge", "task_id": task_id, "attempt": 2, **retry_judge.to_dict()})
                    supporting = select_sources_by_ids(all_run_sources, retry_judge.supporting_source_ids) if retry_judge.answerable else []
                    related_sources = select_sources_by_ids(all_run_sources, retry_judge.related_source_ids) if not retry_judge.answerable else []

                elif decision.should_retry and retry_query and retry_key == key:
                    latency_trace["skip_retry_reason"] = "duplicate_query"
                elif decision.should_retry and not retry_query:
                    latency_trace["skip_retry_reason"] = "empty_retry_query"
                elif not decision.should_retry:
                    latency_trace["skip_retry_reason"] = "reflect_declined_retry"

                local_observations.append(
                    {
                        "type": "rag_reflection",
                        "task_id": task_id,
                        "initial_query": query,
                        "initial_status": "insufficient",
                        "retry_decision": retry_decision,
                        "executed_queries": [str(run.get("query") or "") for run in query_runs if run.get("query")],
                    }
                )

            latency_trace["selected_sources_count"] = len(supporting)
            latency_trace["candidate_sources_count"] = len(all_run_sources)
            latency_trace["supporting_sources_count"] = len(supporting)
            latency_trace["related_sources_count"] = len(related_sources)
            status = "ok" if supporting else "empty"

            for run in query_runs:
                run_query = str(run.get("query") or "")
                run_trace = dict(run.get("trace") or {})
                local_observations.append(
                    {
                        "type": "tool",
                        "tool_name": "search_knowledge_base",
                        "query": run_query,
                        "task": public_search_task(task),
                        "retrieval_trace": run_trace,
                    }
                )
                local_tool_calls.append(
                    {
                        "tool_name": "search_knowledge_base",
                        "args": {"query": run_query, "kb_ids": state.get("used_kbs", [])},
                        "ok": True,
                        "cache_hit": bool(run_trace.get("retrieval_cache_hit")),
                    }
                )

            task_result = {
                "task_id": task_id,
                "kind": "rag",
                "objective": objective,
                "status": status,
                "query": query,
                "executed_queries": [str(run.get("query") or "") for run in query_runs if run.get("query")],
                "sources": supporting,
                "candidate_sources": all_run_sources,
                "related_sources": related_sources,
                "evidence_judgments": evidence_judgments,
                "evidence_summary": build_evidence_summary_from_sources(supporting),
                "related_evidence_summary": build_evidence_summary_from_sources(related_sources),
                "unsupported_reason": (
                    "未找到完整明确依据，但检索到相关内容"
                    if status != "ok" and related_sources
                    else "未检索到足以支持该子目标的证据" if status != "ok" else ""
                ),
                "latency_trace": latency_trace,
            }
            if retry_decision:
                task_result["retry_decision"] = retry_decision
            return {
                "task_id": task_id,
                "status": status,
                "task_result": task_result,
                "supporting_sources": supporting,
                "candidate_sources": all_run_sources,
                "docs": local_docs,
                "executed_queries": local_executed_queries,
                "executed_query_keys": local_executed_keys,
                "cache_updates": local_cache_updates,
                "observations": local_observations,
                "tool_calls": local_tool_calls,
                "llm_calls": list(local_trace_state.get("llm_calls") or []),
            }

        processable = [task for task in pending if normalize_query_key(str(task.get("query") or "")) in by_key]
        processed: list[dict[str, Any]] = []
        max_parallel_tasks = max(1, int(getattr(self.settings, "agent_parallel_rag_tasks", 1) or 1))
        if len(processable) > 1 and max_parallel_tasks > 1:
            with ThreadPoolExecutor(max_workers=min(max_parallel_tasks, len(processable))) as pool:
                future_by_id = {pool.submit(process_task, task): str(task.get("task_id") or "") for task in processable}
                unordered: dict[str, dict[str, Any]] = {}
                for future in as_completed(future_by_id):
                    result = future.result()
                    if result is not None:
                        unordered[str(result.get("task_id") or future_by_id[future])] = result
                for task in processable:
                    task_id = str(task.get("task_id") or "")
                    if task_id in unordered:
                        processed.append(unordered[task_id])
        else:
            for task in processable:
                result = process_task(task)
                if result is not None:
                    processed.append(result)

        supporting_sources: list[dict[str, Any]] = list(state.get("supporting_sources") or state.get("sources") or [])
        candidate_sources: list[dict[str, Any]] = list(state.get("candidate_sources") or [])
        task_results = list(state.get("task_results") or [])
        completed = list(state.get("completed_tasks") or [])

        for result in processed:
            for query in result.get("executed_queries") or []:
                if query and query not in executed_queries:
                    executed_queries.append(query)
            for key in result.get("executed_query_keys") or []:
                if key and key not in executed_query_keys:
                    executed_query_keys.append(key)
            retrieval_cache.update(result.get("cache_updates") or {})
            observations.extend(result.get("observations") or [])
            tool_calls.extend(result.get("tool_calls") or [])
            state.setdefault("llm_calls", []).extend(result.get("llm_calls") or [])
            all_docs.extend(result.get("docs") or [])
            supporting_sources.extend(result.get("supporting_sources") or [])
            candidate_sources.extend(result.get("candidate_sources") or [])
            task_result = result.get("task_result")
            if isinstance(task_result, dict):
                task_results.append(task_result)
            if result.get("status") == "ok" and result.get("task_id") not in completed:
                completed.append(str(result.get("task_id")))

        before_doc_keys = {document_key(doc) for doc in state.get("retrieved_docs", [])}
        all_docs = dedupe_keep_order(all_docs, key=document_key)
        after_doc_keys = {document_key(doc) for doc in all_docs}
        state["retrieval_made_progress"] = bool(after_doc_keys - before_doc_keys)
        supporting_sources = dedupe_sources(supporting_sources)
        candidate_sources = dedupe_sources(candidate_sources)

        state["retrieved_docs"] = all_docs
        state["supporting_sources"] = supporting_sources
        state["candidate_sources"] = candidate_sources
        state["sources"] = supporting_sources
        state["task_results"] = dedupe_task_results(task_results)
        state["completed_tasks"] = completed
        state["executed_queries"] = executed_queries
        state["_executed_query_keys"] = executed_query_keys
        state["_retrieval_cache"] = retrieval_cache
        state["pending_search_tasks"] = []
        state["evidence_brief"] = compact_evidence_text(
            all_docs,
            entities=state.get("entities", []),
            max_total_chars=int(getattr(self.settings, "agent_evidence_char_limit", 4200) or 4200),
        )
        state["supporting_evidence_brief"] = sources_to_evidence_text(supporting_sources)

        rag_latencies = [
            result.get("latency_trace")
            for result in state.get("task_results", [])
            if isinstance(result, dict) and isinstance(result.get("latency_trace"), dict)
        ]
        if rag_latencies:
            state["rag_latency_summary"] = {
                "execution_mode": "parallel" if len(processed) > 1 and max_parallel_tasks > 1 else "sequential",
                "parallel_rag_tasks": len(processed) if len(processed) > 1 and max_parallel_tasks > 1 else 1,
                "service_wall_ms": round((time.perf_counter() - service_started) * 1000, 2),
                "next_action_total_ms": round(sum(float(item.get("next_action_ms") or 0) for item in rag_latencies), 2),
                "retrieve_total_ms": round(sum(float(item.get("retrieve_1_ms") or 0) + float(item.get("retrieve_2_ms") or 0) for item in rag_latencies), 2),
                "evidence_judge_total_ms": round(sum(float(item.get("evidence_judge_1_ms") or 0) + float(item.get("evidence_judge_2_ms") or 0) for item in rag_latencies), 2),
                "rag_reflect_total_ms": round(sum(float(item.get("rag_reflect_ms") or 0) for item in rag_latencies), 2),
                "related_sources_total": sum(int(item.get("related_sources_count") or 0) for item in rag_latencies),
                "triggered_reflect_count": sum(1 for item in rag_latencies if item.get("triggered_reflect")),
                "retry_executed_count": sum(1 for item in rag_latencies if item.get("retry_executed")),
            }
        return state
