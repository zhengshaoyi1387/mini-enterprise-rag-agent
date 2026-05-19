from __future__ import annotations

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

    Outer ReAct selects the RAG task. This service owns the inner RAG ReAct loop:
    retrieve -> LLM evidence judge -> same-topic retrieval rewrite -> retry -> judge.
    Code only enforces hard guardrails such as permissions, retry budget, JSON/schema
    validity, and candidate/supporting evidence separation.
    """

    def __init__(
        self,
        settings: Settings,
        get_retriever: Callable[[], Any],
        get_role_policies: Callable[[dict[str, Any]], Any],
        *,
        llm: Any | None = None,
    ) -> None:
        self.settings = settings
        self._get_retriever = get_retriever
        self._get_role_policies = get_role_policies
        self.llm = llm

    def retrieve(self, state: dict[str, Any]) -> dict[str, Any]:
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

        pending = list(state.get("pending_search_tasks") or [])
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
        model_name = str(getattr(self.settings, "qwen_control_model", None) or getattr(self.settings, "qwen_chat_model", "control_llm") or "control_llm")

        runnable: list[dict[str, Any]] = []
        cached_by_key: dict[str, tuple[list[Any], dict[str, Any]]] = {}
        existing_keys = set(str(x) for x in executed_query_keys)

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
                if trace.get("rerank_enabled"):
                    trace["rerank_cache_hit"] = True
                cached_by_key[key] = (docs, trace)
            elif key not in existing_keys:
                runnable.append(task)
            existing_keys.add(key)

        def run_task(task: dict[str, Any]) -> tuple[dict[str, Any], list[Any], dict[str, Any]]:
            query = str(task.get("query") or "").strip()
            top_k = int(task.get("top_k") or self.settings.top_k)
            candidate_k = int(task.get("candidate_k") or self.settings.candidate_k)
            enable_rerank = task.get("enable_rerank", state.get("enable_rerank"))
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
            return task, list(docs or []), trace

        results: list[tuple[dict[str, Any], list[Any], dict[str, Any]]] = []
        max_workers = max(1, int(getattr(self.settings, "agent_retrieval_workers", 1) or 1))
        if len(runnable) > 1 and max_workers > 1:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable))) as pool:
                futures = [pool.submit(run_task, task) for task in runnable]
                for future in as_completed(futures):
                    results.append(future.result())
        else:
            for task in runnable:
                results.append(run_task(task))

        by_key: dict[str, tuple[dict[str, Any], list[Any], dict[str, Any]]] = {}
        for task, docs, trace in results:
            by_key[normalize_query_key(str(task.get("query") or ""))] = (task, docs, trace)
        for task in pending:
            query = str(task.get("query") or "").strip()
            key = normalize_query_key(query)
            if key in cached_by_key:
                docs, trace = cached_by_key[key]
                by_key[key] = (task, docs, trace)

        supporting_sources: list[dict[str, Any]] = list(state.get("supporting_sources") or state.get("sources") or [])
        candidate_sources: list[dict[str, Any]] = list(state.get("candidate_sources") or [])
        task_results = list(state.get("task_results") or [])
        completed = list(state.get("completed_tasks") or [])

        for task in pending:
            query = str(task.get("query") or "").strip()
            key = normalize_query_key(query)
            if key not in by_key:
                continue
            _, docs, trace = by_key[key]
            if query not in executed_queries:
                executed_queries.append(query)
            if key not in executed_query_keys:
                executed_query_keys.append(key)
            if cache_enabled:
                retrieval_cache[key] = {"docs": list(docs), "trace": dict(trace)}

            task_id = str(task.get("task_id") or "") or f"rag_{len(task_results) + 1}"
            objective = str(task.get("objective") or query)
            original_question = str(state.get("question") or query)
            allowed_kbs = [str(kb) for kb in (state.get("used_kbs") or [])]
            query_runs: list[dict[str, Any]] = []
            evidence_judgments: list[dict[str, Any]] = []
            retry_decision: dict[str, Any] | None = None

            srcs = [document_to_source(doc) for doc in docs]
            query_runs.append({"query": query, "docs": docs, "trace": trace, "sources": srcs})
            all_run_sources = list(srcs)

            judge = judge_rag_evidence_with_llm(
                original_question=original_question,
                rag_task_objective=objective,
                candidate_sources=all_run_sources,
                llm=self.llm,
                attempt=1,
                trace_state=state,
                model_name=model_name,
            )
            evidence_judgments.append({"attempt": 1, **judge.to_dict()})
            observations.append(
                {
                    "type": "rag_evidence_judge",
                    "task_id": task_id,
                    "attempt": 1,
                    **judge.to_dict(),
                }
            )
            supporting = select_sources_by_ids(all_run_sources, judge.supporting_source_ids) if judge.answerable else []

            if not judge.answerable or judge.sufficiency == "low":
                decision = maybe_rewrite_rag_query(
                    question=original_question,
                    task=task,
                    initial_query=query,
                    candidate_sources=all_run_sources,
                    unsupported_reason=judge.reason or "候选证据不足以回答原问题",
                    missing_evidence=list(judge.missing_evidence),
                    allowed_kbs=allowed_kbs,
                    llm=self.llm,
                    trace_state=state,
                    model_name=model_name,
                )
                retry_decision = decision.to_dict()
                if decision.should_retry and decision.retrieval_query:
                    retry_query = str(decision.retrieval_query)
                    retry_key = normalize_query_key(retry_query)
                    if retry_key and retry_key != key and retry_key not in set(executed_query_keys):
                        retry_task = dict(task)
                        retry_task["query"] = retry_query
                        retry_task["target_kbs"] = list(decision.target_kbs)
                        _, retry_docs, retry_trace = run_task(retry_task)
                        retry_srcs = [document_to_source(doc) for doc in retry_docs]
                        query_runs.append({"query": retry_query, "docs": retry_docs, "trace": retry_trace, "sources": retry_srcs})
                        all_run_sources.extend(retry_srcs)
                        if retry_query not in executed_queries:
                            executed_queries.append(retry_query)
                        if retry_key not in executed_query_keys:
                            executed_query_keys.append(retry_key)
                        if cache_enabled:
                            retrieval_cache[retry_key] = {"docs": list(retry_docs), "trace": dict(retry_trace)}
                        retry_judge = judge_rag_evidence_with_llm(
                            original_question=original_question,
                            rag_task_objective=objective,
                            candidate_sources=all_run_sources,
                            llm=self.llm,
                            attempt=2,
                            trace_state=state,
                            model_name=model_name,
                        )
                        evidence_judgments.append({"attempt": 2, **retry_judge.to_dict()})
                        observations.append(
                            {
                                "type": "rag_evidence_judge",
                                "task_id": task_id,
                                "attempt": 2,
                                **retry_judge.to_dict(),
                            }
                        )
                        supporting = select_sources_by_ids(all_run_sources, retry_judge.supporting_source_ids) if retry_judge.answerable else []
                observations.append(
                    {
                        "type": "rag_reflection",
                        "task_id": task_id,
                        "initial_query": query,
                        "initial_status": "insufficient",
                        "retry_decision": retry_decision,
                        "executed_queries": [run.get("query") for run in query_runs],
                    }
                )

            status = "ok" if supporting else "empty"

            for run in query_runs:
                run_query = str(run.get("query") or "")
                run_trace = dict(run.get("trace") or {})
                observations.append(
                    {
                        "type": "tool",
                        "tool_name": "search_knowledge_base",
                        "query": run_query,
                        "task": public_search_task(task),
                        "retrieval_trace": run_trace,
                    }
                )
                tool_calls.append(
                    {
                        "tool_name": "search_knowledge_base",
                        "args": {"query": run_query, "kb_ids": state.get("used_kbs", [])},
                        "ok": True,
                        "cache_hit": bool(run_trace.get("retrieval_cache_hit")),
                    }
                )
                all_docs.extend(run.get("docs") or [])

            supporting_sources.extend(supporting)
            candidate_sources.extend(all_run_sources)
            if status == "ok" and task_id not in completed:
                completed.append(task_id)

            task_result = {
                "task_id": task_id,
                "kind": "rag",
                "objective": objective,
                "status": status,
                "query": query,
                "executed_queries": [str(run.get("query") or "") for run in query_runs if run.get("query")],
                "sources": supporting,
                "candidate_sources": all_run_sources,
                "evidence_judgments": evidence_judgments,
                "evidence_summary": build_evidence_summary_from_sources(supporting),
                "unsupported_reason": "未检索到足以支持该子目标的证据" if status != "ok" else "",
            }
            if retry_decision:
                task_result["retry_decision"] = retry_decision
            task_results.append(task_result)

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
        return state
