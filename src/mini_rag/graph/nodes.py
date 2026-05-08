from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from mini_rag.agent.context_store import SQLiteContextStore
from mini_rag.config import Settings
from mini_rag.graph.prompts import (
    GENERATE_ANSWER_SYSTEM,
    MEMORY_UPDATE_SYSTEM,
    PLAN_RETRIEVAL_SYSTEM,
    REFLECT_EVIDENCE_SYSTEM,
    ROUTE_SYSTEM,
    UNDERSTAND_QUERY_SYSTEM,
    format_answer_user,
    format_memory_user,
    format_plan_user,
    format_reflect_user,
    format_route_user,
    format_understand_user,
)
from mini_rag.graph.state import AgentState
from mini_rag.graph.utils import (
    NodeTimer,
    coerce_list,
    compact_evidence_text,
    dedupe_keep_order,
    document_key,
    document_to_source,
    format_evidence_text,
    get_message_content,
    safe_json_loads,
    strip_citations_and_metadata,
    truncate,
)
from mini_rag.utils import stable_hash
from mini_rag.security.auth_store import SQLiteAuthStore
from mini_rag.security.permissions import assert_can_access_kbs, assert_tool_permission, normalize_role
from mini_rag.tools.daily_tools import build_default_tool_registry, select_daily_tool_by_rule
from mini_rag.tools.datetime_tool import get_current_datetime


class AgenticRAGNodes:
    """Agentic RAG 的 LangGraph 节点集合。

    LLM 负责语义理解、检索规划、证据反思和最终表达；
    代码负责状态隔离、结构化解析、检索执行、去重、trace 和记忆清洗。
    """

    def __init__(self, settings: Settings, llm: Any | None = None, retriever: Any | None = None):
        self.settings = settings
        self.context_store = SQLiteContextStore(settings.context_db_path)
        if llm is None:
            from mini_rag.models.qwen import build_qwen_chat_model, build_qwen_control_model

            self.answer_llm = build_qwen_chat_model(settings)
            self.control_llm = build_qwen_control_model(settings)
        else:
            # 测试或自定义运行时可注入一个假 LLM；默认同时承担控制节点和最终回答。
            self.answer_llm = llm
            self.control_llm = llm
        self.llm = self.answer_llm
        self.retriever: Any | None = retriever
        self.tool_registry = build_default_tool_registry()
        self.auth_store = SQLiteAuthStore(settings.auth_db_path)

    # ---------- public LangGraph nodes ----------
    def load_context(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "load_context"):
            session_id = state.get("session_id")
            context = self.context_store.get_context(session_id, max_turns=self.settings.session_max_turns)
            state["conversation_summary"] = context.summary
            state["history"] = [self._turn_to_history_item(turn) for turn in context.turns]
            state.setdefault("observations", [])
            state.setdefault("node_trace", [])
            state.setdefault("tool_calls", [])
            state.setdefault("retrieved_docs", [])
            state.setdefault("sources", [])
            state.setdefault("evidence_brief", "")
            state.setdefault("executed_queries", [])
            state.setdefault("_executed_query_keys", [])
            state.setdefault("_retrieval_cache", {})
            state.setdefault("llm_calls", [])
            state.setdefault("reflect_round", 0)
        return state

    def check_permission(self, state: AgentState) -> AgentState:
        """Compute allowed knowledge bases before any retrieval node runs.

        Permission rules live at the KB level. This node never retrieves
        documents; it only converts role + requested_kbs into allowed_kbs.
        Later retriever calls receive allowed_kbs so unauthorized chunks are not
        fetched into context.
        """

        with NodeTimer(state, "check_permission"):
            role = normalize_role(state.get("role"))
            requested_kbs = state.get("requested_kbs") or []
            try:
                allowed_kbs = assert_can_access_kbs(role, requested_kbs, role_policies=self.auth_store.list_role_policies())
                state["allowed_kbs"] = allowed_kbs
                state["used_kbs"] = allowed_kbs
                state.setdefault("audit_events", []).append(
                    {
                        "event": "kb_permission_check",
                        "role": role,
                        "requested_kbs": requested_kbs,
                        "allowed_kbs": allowed_kbs,
                        "decision": "allowed",
                    }
                )
                state.setdefault("observations", []).append(
                    {"type": "kb_permission_check", "role": role, "requested_kbs": requested_kbs, "allowed_kbs": allowed_kbs}
                )
            except PermissionError as exc:
                state["route"] = "reject"
                state["risk_level"] = "medium"
                state["error"] = str(exc)
                state["final_answer"] = "你没有权限访问所请求的知识库。"
                state.setdefault("allowed_kbs", [])
                state.setdefault("used_kbs", [])
                state.setdefault("audit_events", []).append(
                    {
                        "event": "kb_permission_check",
                        "role": role,
                        "requested_kbs": requested_kbs,
                        "decision": "blocked",
                        "reason": str(exc),
                    }
                )
        return state

    def understand_query(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "understand_query"):
            if state.get("error") and state.get("route") == "reject":
                return state
            question = state.get("question", "")
            selected_tool = select_daily_tool_by_rule(question)
            if selected_tool:
                state["intent"] = "tool"
                state["route"] = "tool"  # type: ignore[assignment]
                state["risk_level"] = "low"
                state["required_tools"] = [selected_tool]
                state["selected_tool"] = selected_tool
                state["standalone_query"] = question
                state["topic"] = selected_tool
                state["entities"] = []
                state["query_reason"] = "规则命中低风险办公工具，跳过 LLM 理解节点以降低延迟。"
                state["router_reason"] = state["query_reason"]
                state.setdefault("observations", []).append(
                    {"type": "understanding", "intent": "tool", "route": "tool", "selected_tool": selected_tool, "reason": state["query_reason"]}
                )
                return state
            user_prompt = format_understand_user(
                question=question,
                summary=state.get("conversation_summary", ""),
                history=state.get("history", []),
            )
            payload = self._invoke_json(
                state=state,
                node="understand_query",
                system=UNDERSTAND_QUERY_SYSTEM,
                user=user_prompt,
                default={
                    "intent": "rag_fact",
                    "route": "rag",
                    "standalone_query": question,
                    "topic": "",
                    "entities": [],
                    "needs_retrieval": True,
                    "risk_level": "low",
                    "required_tools": [],
                    "selected_tool": None,
                    "tool_input": {},
                    "reason": "LLM 输出解析失败，使用原问题兜底。",
                },
            )
            intent = str(payload.get("intent") or "rag_fact")
            standalone_query = str(payload.get("standalone_query") or question).strip() or question
            entities = [str(x).strip() for x in coerce_list(payload.get("entities")) if str(x).strip()]
            route = str(payload.get("route") or ("rag" if payload.get("needs_retrieval", True) else "direct"))
            if route not in {"direct", "rag", "tool", "reject"}:
                route = "rag"
            if self._is_dangerous_question(question, standalone_query):
                route = "reject"
                payload["risk_level"] = "high"
            state["intent"] = intent
            state["route"] = route  # type: ignore[assignment]
            state["risk_level"] = str(payload.get("risk_level") or "low")
            state["required_tools"] = [str(x) for x in coerce_list(payload.get("required_tools"))]
            state["selected_tool"] = str(payload.get("selected_tool") or "") or None
            state["tool_input"] = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
            # Obvious daily business requests are routed by cheap deterministic rules.
            # RAG policy questions remain on the retrieval route.
            selected_tool = select_daily_tool_by_rule(question)
            if selected_tool and route != "reject":
                route = "tool"
                state["route"] = "tool"  # type: ignore[assignment]
                state["selected_tool"] = selected_tool
                state["required_tools"] = [selected_tool]
            state["standalone_query"] = standalone_query
            state["topic"] = str(payload.get("topic") or "")
            state["entities"] = dedupe_keep_order(entities)
            state["query_reason"] = str(payload.get("reason") or "")
            state["router_reason"] = str(payload.get("reason") or "")
            state.setdefault("observations", []).append(
                {
                    "type": "understanding",
                    "intent": state["intent"],
                    "route": state["route"],
                    "standalone_query": state["standalone_query"],
                    "topic": state["topic"],
                    "entities": state["entities"],
                    "reason": state["query_reason"],
                }
            )
        return state

    def route(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "route"):
            if state.get("error") and state.get("route") == "reject":
                return state
            # route 已由 understand_query 的同一次 LLM 调用产出；这里仅做安全校验和 trace 分隔。
            route = str(state.get("route") or "rag")
            if route not in {"direct", "rag", "tool", "reject"}:
                route = "rag"
            if self._is_dangerous_question(state.get("question", ""), state.get("standalone_query", "")):
                route = "reject"
                state["risk_level"] = "high"
            selected_tool = select_daily_tool_by_rule(state.get("question", ""))
            if selected_tool and route != "reject":
                route = "tool"
                state["selected_tool"] = selected_tool
                state["required_tools"] = [selected_tool]
            state["route"] = route  # type: ignore[assignment]
            state.setdefault("risk_level", "low")
            state.setdefault("required_tools", [])
            state.setdefault("router_reason", state.get("query_reason", ""))
            state.setdefault("observations", []).append(
                {"type": "route", "route": route, "risk_level": state["risk_level"], "reason": state["router_reason"]}
            )
        return state

    def call_tool(self, state: AgentState) -> AgentState:
        """Execute a low-risk office tool through a registry with permission checks."""

        with NodeTimer(state, "call_tool"):
            role = normalize_role(state.get("role"))
            tool_name = str(state.get("selected_tool") or (state.get("required_tools") or [None])[0] or "")
            if not tool_name:
                state["route"] = "reject"
                state["error"] = "No tool selected"
                state["final_answer"] = "没有识别到可执行的办公工具。"
                return state
            try:
                assert_tool_permission(role, tool_name, role_policies=self.auth_store.list_role_policies())
                payload = self._build_tool_payload(state, tool_name, role)
                result = self.tool_registry.invoke(tool_name, payload)
                content = str(result.get("content") or self._format_tool_result(tool_name, result))
                state["final_answer"] = content
                state.setdefault("tool_calls", []).append(
                    {
                        "tool_name": tool_name,
                        "args": payload,
                        "ok": not bool(result.get("error")),
                        "risk_level": result.get("risk_level", "low"),
                        "error": result.get("error"),
                    }
                )
                state.setdefault("observations", []).append({"type": "tool", "tool_name": tool_name, "result": result})
                state.setdefault("audit_events", []).append(
                    {
                        "event": "tool_call",
                        "tool_name": tool_name,
                        "role": role,
                        "decision": "blocked" if result.get("error") == "permission denied" else "allowed",
                        "action": result.get("action"),
                        "reason": result.get("error"),
                    }
                )
            except PermissionError as exc:
                state["route"] = "reject"
                state["error"] = str(exc)
                state["final_answer"] = f"你没有权限调用工具：{tool_name}"
                state.setdefault("tool_calls", []).append({"tool_name": tool_name, "ok": False, "reason": str(exc)})
                state.setdefault("audit_events", []).append(
                    {"event": "tool_call", "tool_name": tool_name, "role": role, "decision": "blocked", "reason": str(exc)}
                )
        return state

    def plan_retrieval(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "plan_retrieval"):
            user_prompt = format_plan_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                intent=state.get("intent", ""),
                topic=state.get("topic", ""),
                entities=state.get("entities", []),
            )
            payload = self._invoke_json(
                state=state,
                node="plan_retrieval",
                system=PLAN_RETRIEVAL_SYSTEM,
                user=user_prompt,
                default={
                    "search_tasks": [
                        {
                            "query": state.get("standalone_query") or state.get("question", ""),
                            "purpose": "answer_question",
                            "target_entity": None,
                        }
                    ],
                    "reason": "检索规划解析失败，使用独立问题兜底。",
                },
            )
            raw_tasks = payload.get("search_tasks")
            if raw_tasks is None:
                raw_tasks = payload.get("search_queries")
            tasks = self._normalize_tasks(raw_tasks, fallback_query=state.get("standalone_query") or state.get("question", ""))
            tasks = self._optimize_search_tasks(state, tasks)
            state["search_tasks"] = tasks
            state["pending_search_tasks"] = tasks
            state.setdefault("observations", []).append({"type": "retrieval_plan", "search_tasks": tasks, "reason": payload.get("reason", "")})
        return state

    def retrieve(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "retrieve"):
            # RAG retrieval is treated as a tool-like action. The model may
            # route to retrieval, but program-side permission is checked here
            # immediately before executing the underlying retriever.
            role = normalize_role(state.get("role"))
            assert_tool_permission(role, "search_knowledge_base", role_policies=self.auth_store.list_role_policies())
            state.setdefault("observations", []).append(
                {
                    "type": "permission_check",
                    "scope": "tool",
                    "tool_name": "search_knowledge_base",
                    "role": role,
                    "allowed": True,
                }
            )
            retriever = self._get_retriever()
            pending = state.get("pending_search_tasks") or []
            if not pending:
                state.setdefault("observations", []).append({"type": "retrieve", "message": "没有待检索任务，跳过。"})
                return state

            all_docs = list(state.get("retrieved_docs") or [])
            previous_doc_count = len(dedupe_keep_order(all_docs, key=document_key))
            executed_queries = list(state.get("executed_queries") or [])
            executed_query_keys = list(state.get("_executed_query_keys") or [])
            sources = list(state.get("sources") or [])
            tool_calls = state.setdefault("tool_calls", [])
            observations = state.setdefault("observations", [])
            executed_set = set(executed_query_keys)
            retrieval_cache = state.setdefault("_retrieval_cache", {})
            cache_enabled = bool(getattr(self.settings, "agent_enable_retrieval_cache", True))

            runnable_tasks: list[dict[str, Any]] = []
            for task in pending:
                query = str(task.get("query") or "").strip()
                query_key = self._normalize_query_key(query)
                if not query:
                    continue
                if cache_enabled and query_key in retrieval_cache:
                    cached = retrieval_cache[query_key]
                    docs = list(cached.get("docs") or [])
                    retrieval_trace = dict(cached.get("trace") or {})
                    retrieval_trace["retrieval_cache_hit"] = True
                    if retrieval_trace.get("rerank_enabled"):
                        retrieval_trace["rerank_cache_hit"] = True
                    retrieval_trace["query"] = query
                    executed_queries.append(query)
                    executed_query_keys.append(query_key)
                    tool_calls.append({"tool_name": "search_knowledge_base", "args": {"query": query, "kb_ids": state.get("used_kbs", [])}, "ok": True, "cache_hit": True})
                    observations.append(
                        {
                            "type": "tool",
                            "tool_name": "search_knowledge_base",
                            "query": query,
                            "task": task,
                            "retrieval_trace": retrieval_trace,
                        }
                    )
                    all_docs.extend(docs)
                    continue
                if query_key in executed_set:
                    continue
                runnable_tasks.append(task)
                executed_set.add(query_key)

            def run_task(task: dict[str, Any]) -> tuple[dict[str, Any], list[Any], dict[str, Any]]:
                query = str(task.get("query") or "").strip()
                top_k = int(task.get("top_k") or self.settings.top_k)
                candidate_k = int(task.get("candidate_k") or self.settings.candidate_k)
                enable_rerank = task.get("enable_rerank", state.get("enable_rerank"))
                try:
                    docs, retrieval_trace = retriever.search(
                        query,
                        top_k=top_k,
                        candidate_k=candidate_k,
                        retrieval_mode=state.get("retrieval_mode"),
                        enable_rerank=enable_rerank,
                        kb_ids=state.get("used_kbs", []),
                    )
                except TypeError as exc:
                    if "unexpected keyword argument" not in str(exc):
                        raise
                    try:
                        docs, retrieval_trace = retriever.search(
                            query,
                            retrieval_mode=state.get("retrieval_mode"),
                            enable_rerank=enable_rerank,
                            kb_ids=state.get("used_kbs", []),
                        )
                    except TypeError as second_exc:
                        if "unexpected keyword argument" not in str(second_exc):
                            raise
                        docs, retrieval_trace = retriever.search(
                            query,
                            retrieval_mode=state.get("retrieval_mode"),
                            enable_rerank=enable_rerank,
                        )
                retrieval_trace.setdefault("retrieval_cache_hit", False)
                retrieval_trace.setdefault("rerank_cache_hit", False)
                return task, docs, retrieval_trace

            def record_result(task: dict[str, Any], docs: list[Any], retrieval_trace: dict[str, Any]) -> None:
                query = str(task.get("query") or "").strip()
                query_key = self._normalize_query_key(query)
                executed_queries.append(query)
                executed_query_keys.append(query_key)
                if cache_enabled:
                    retrieval_cache[query_key] = {"docs": list(docs), "trace": dict(retrieval_trace)}
                tool_calls.append({"tool_name": "search_knowledge_base", "args": {"query": query, "kb_ids": state.get("used_kbs", [])}, "ok": True})
                observations.append(
                    {
                        "type": "tool",
                        "tool_name": "search_knowledge_base",
                        "query": query,
                        "task": task,
                        "retrieval_trace": retrieval_trace,
                    }
                )
                all_docs.extend(docs)

            max_workers = max(1, int(getattr(self.settings, "agent_retrieval_workers", 1) or 1))
            if len(runnable_tasks) > 1 and max_workers > 1:
                with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable_tasks))) as pool:
                    futures = [pool.submit(run_task, task) for task in runnable_tasks]
                    for future in as_completed(futures):
                        task, docs, retrieval_trace = future.result()
                        record_result(task, docs, retrieval_trace)
            else:
                for task in runnable_tasks:
                    task, docs, retrieval_trace = run_task(task)
                    record_result(task, docs, retrieval_trace)

            all_docs = dedupe_keep_order(all_docs, key=document_key)
            state["retrieval_made_progress"] = len(all_docs) > previous_doc_count
            sources = [document_to_source(doc) for doc in all_docs]
            state["retrieved_docs"] = all_docs
            state["sources"] = sources
            state["executed_queries"] = executed_queries
            state["_executed_query_keys"] = executed_query_keys
            state["_retrieval_cache"] = retrieval_cache
            state["pending_search_tasks"] = []
            state["evidence_brief"] = compact_evidence_text(
                all_docs,
                entities=state.get("entities", []),
                max_total_chars=int(getattr(self.settings, "agent_evidence_char_limit", 4200) or 4200),
            )
        return state

    def reflect_evidence(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "reflect_evidence"):
            reflect_round = int(state.get("reflect_round") or 0) + 1
            state["reflect_round"] = reflect_round
            evidence_text = state.get("evidence_brief") or compact_evidence_text(state.get("retrieved_docs", []), entities=state.get("entities", []))
            user_prompt = format_reflect_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                executed_queries=state.get("executed_queries", []),
                evidence_text=evidence_text,
            )
            payload = self._invoke_json(
                state=state,
                node="reflect_evidence",
                system=REFLECT_EVIDENCE_SYSTEM,
                user=user_prompt,
                default={
                    "is_sufficient": bool(state.get("retrieved_docs")),
                    "can_answer_partial": bool(state.get("retrieved_docs")),
                    "should_continue_retrieval": False,
                    "missing_information": [],
                    "followup_tasks": [],
                    "stop_reason": "证据反思解析失败，基于现有证据进入回答。",
                    "reason": "证据反思解析失败，基于现有证据进入回答。",
                },
            )
            followup_tasks = self._normalize_tasks(payload.get("followup_tasks"), fallback_query="")
            if not followup_tasks and payload.get("followup_queries") is not None:
                followup_tasks = self._normalize_tasks(payload.get("followup_queries"), fallback_query="")
            executed = set(state.get("executed_queries", []))
            executed_keys = set(state.get("_executed_query_keys", []))
            followup_tasks = [
                task for task in followup_tasks
                if str(task.get("query", "")).strip() not in executed
                and self._normalize_query_key(str(task.get("query", ""))) not in executed_keys
            ]
            max_followups = max(0, int(getattr(self.settings, "agent_max_followup_tasks", 2) or 0))
            followup_tasks = followup_tasks[:max_followups]
            can_answer_partial = bool(payload.get("can_answer_partial"))
            is_sufficient = bool(payload.get("is_sufficient"))
            should_continue = bool(payload.get("should_continue_retrieval"))
            if "should_continue_retrieval" not in payload:
                should_continue = bool(followup_tasks) and not is_sufficient
            stop_reason = str(payload.get("stop_reason") or "")
            if is_sufficient or not should_continue:
                followup_tasks = []
                stop_reason = stop_reason or ("evidence_sufficient" if is_sufficient else "llm_decided_no_more_retrieval")
            # 循环边界由代码控制；LLM 只能建议 followup_tasks。
            if reflect_round >= max(1, int(getattr(self.settings, "agent_reflect_max_rounds", 1) or 1)):
                followup_tasks = []
                stop_reason = stop_reason or "max_reflection_rounds_reached"
            state["evidence_assessment"] = {
                "is_sufficient": is_sufficient,
                "can_answer_partial": can_answer_partial,
                "should_continue_retrieval": should_continue,
                "missing_information": [str(x) for x in coerce_list(payload.get("missing_information"))],
                "followup_tasks": followup_tasks,
                "reason": str(payload.get("reason") or ""),
            }
            if stop_reason:
                state["evidence_assessment"]["stop_reason"] = stop_reason
            state["pending_search_tasks"] = followup_tasks
            state.setdefault("observations", []).append({"type": "evidence_reflection", **state["evidence_assessment"]})
        return state

    def generate_answer(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "generate_answer"):
            if state.get("route") == "reject":
                state["final_answer"] = state.get("final_answer") or "抱歉，这个请求存在安全风险，我不能执行。"
                return state
            if state.get("route") == "tool":
                state["final_answer"] = state.get("final_answer") or "工具已执行，但没有返回可展示内容。"
                return state
            evidence_text = state.get("evidence_brief") or compact_evidence_text(state.get("retrieved_docs", []), entities=state.get("entities", []))
            user_prompt = format_answer_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                route=state.get("route", "direct"),
                model_name=self.settings.qwen_chat_model,
                evidence_assessment=state.get("evidence_assessment", {}),
                evidence_text=evidence_text,
            )
            answer = self._invoke_text(
                state=state,
                node="generate_answer",
                system=GENERATE_ANSWER_SYSTEM,
                user=user_prompt,
                llm=self.answer_llm,
                model_name=self.settings.qwen_chat_model,
            )
            state["final_answer"] = answer.strip() or "抱歉，我暂时无法生成回答。"
        return state

    def stream_generate_answer(self, state: AgentState):
        with NodeTimer(state, "generate_answer"):
            if state.get("route") == "reject":
                state["final_answer"] = state.get("final_answer") or "抱歉，这个请求存在安全风险，我不能执行。"
                yield state["final_answer"]
                return
            if state.get("route") == "tool":
                state["final_answer"] = state.get("final_answer") or "工具已执行，但没有返回可展示内容。"
                yield state["final_answer"]
                return

            evidence_text = state.get("evidence_brief") or compact_evidence_text(state.get("retrieved_docs", []), entities=state.get("entities", []))
            user_prompt = format_answer_user(
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                route=state.get("route", "direct"),
                model_name=self.settings.qwen_chat_model,
                evidence_assessment=state.get("evidence_assessment", {}),
                evidence_text=evidence_text,
            )

            start = time.perf_counter()
            chunks: list[str] = []
            llm = self.answer_llm
            if hasattr(llm, "stream"):
                for chunk in llm.stream([("system", GENERATE_ANSWER_SYSTEM), ("user", user_prompt)]):
                    content = get_message_content(chunk)
                    if not content:
                        continue
                    chunks.append(content)
                    yield content
                answer = "".join(chunks).strip()
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
                state.setdefault("llm_calls", []).append(
                    {
                        "node": "generate_answer",
                        "model": self.settings.qwen_chat_model,
                        "prompt_chars": len(GENERATE_ANSWER_SYSTEM) + len(user_prompt),
                        "output_chars": len(answer),
                        "latency_ms": elapsed_ms,
                        "streaming": True,
                    }
                )
            else:
                answer = self._invoke_text(
                    state=state,
                    node="generate_answer",
                    system=GENERATE_ANSWER_SYSTEM,
                    user=user_prompt,
                    llm=llm,
                    model_name=self.settings.qwen_chat_model,
                ).strip()
                if answer:
                    yield answer
            state["final_answer"] = answer or "抱歉，我暂时无法生成回答。"

    def update_memory(self, state: AgentState) -> AgentState:
        with NodeTimer(state, "update_memory"):
            answer = state.get("final_answer", "")
            old_summary = state.get("conversation_summary", "")
            route = state.get("route", "direct")

            should_use_lightweight_memory = self._should_use_lightweight_memory(state)
            if should_use_lightweight_memory:
                memory_answer = strip_citations_and_metadata(answer)
                topic = state.get("topic", "")
                entities = state.get("entities", [])
                summary = old_summary or ""
            else:
                user_prompt = format_memory_user(
                    question=state.get("question", ""),
                    standalone_query=state.get("standalone_query", ""),
                    answer=truncate(answer, 1600),
                    old_summary=old_summary,
                )
                payload = self._invoke_json(
                    state=state,
                    node="update_memory",
                    system=MEMORY_UPDATE_SYSTEM,
                    user=user_prompt,
                    default={
                        "memory_answer": strip_citations_and_metadata(answer),
                        "summary": old_summary,
                        "topic": state.get("topic", ""),
                        "entities": state.get("entities", []),
                    },
                )
                memory_answer = str(payload.get("memory_answer") or strip_citations_and_metadata(answer))
                summary = str(payload.get("summary") or old_summary)
                topic = str(payload.get("topic") or state.get("topic", ""))
                entities = [str(x) for x in coerce_list(payload.get("entities") or state.get("entities", []))]

            state["memory_update"] = {
                "memory_answer": memory_answer,
                "summary": summary,
                "topic": topic,
                "entities": entities,
            }
            session_id = state.get("session_id")
            if session_id:
                self.context_store.update_summary(session_id, summary)
                self.context_store.append_turn(
                    session_id=session_id,
                    question=state.get("question", ""),
                    standalone_query=state.get("standalone_query", state.get("question", "")),
                    answer=answer,
                    sources=state.get("sources", []),
                    trace=self.build_trace(state),
                    memory_answer=memory_answer,
                    intent=state.get("intent", ""),
                    topic=topic,
                    entities=entities,
                )
        return state

    # ---------- routing helpers ----------
    def next_after_route(self, state: AgentState) -> str:
        route = state.get("route") or "rag"
        if route == "tool":
            return "call_tool"
        if route == "rag":
            return "plan_retrieval"
        return "generate_answer"

    def should_retrieve(self, state: AgentState) -> str:
        """Backward-compatible helper used by older tests."""
        route = state.get("route") or "rag"
        if route in {"direct", "reject", "tool"}:
            return "generate_answer"
        return "plan_retrieval"

    def after_retrieve(self, state: AgentState) -> str:
        if self._can_skip_reflection(state):
            return "generate_answer"
        return "reflect_evidence"

    def after_reflect(self, state: AgentState) -> str:
        pending = state.get("pending_search_tasks") or []
        max_rounds = max(1, int(getattr(self.settings, "agent_reflect_max_rounds", 1) or 1))
        if pending and int(state.get("reflect_round") or 0) < max_rounds:
            return "retrieve"
        return "generate_answer"

    # ---------- trace/result ----------
    def build_trace(self, state: AgentState) -> dict[str, Any]:
        return {
            "mode": "agentic_rag_langgraph",
            "trace_id": state.get("trace_id"),
            "user_id": state.get("user_id"),
            "role": state.get("role"),
            "question": state.get("question"),
            "session_id": state.get("session_id"),
            "workflow_run_id": state.get("workflow_run_id"),
            "requested_kbs": state.get("requested_kbs", []),
            "allowed_kbs": state.get("allowed_kbs", []),
            "used_kbs": state.get("used_kbs", []),
            "route": state.get("route"),
            "intent": state.get("intent"),
            "risk_level": state.get("risk_level"),
            "standalone_query": state.get("standalone_query"),
            "topic": state.get("topic"),
            "entities": state.get("entities", []),
            "search_tasks": state.get("search_tasks", []),
            "executed_queries": state.get("executed_queries", []),
            "evidence_brief_chars": len(state.get("evidence_brief", "") or ""),
            "evidence_assessment": state.get("evidence_assessment", {}),
            "skipped_reflection_reason": state.get("skipped_reflection_reason"),
            "node_trace": state.get("node_trace", []),
            "llm_calls": state.get("llm_calls", []),
            "total_latency_ms": round(sum(float(item.get("latency_ms") or 0) for item in state.get("node_trace", [])), 2),
            "selected_tool": state.get("selected_tool"),
            "tool_calls": state.get("tool_calls", []),
            "observations": state.get("observations", []),
            "audit_events": state.get("audit_events", []),
            "sources": state.get("sources", []),
            "answer": state.get("final_answer", ""),
            "error": state.get("error"),
        }

    # ---------- internals ----------
    def _build_tool_payload(self, state: AgentState, tool_name: str, role: str) -> dict[str, Any]:
        question = state.get("question", "")
        payload = dict(state.get("tool_input") or {})
        payload.update({"query": question, "user_id": state.get("user_id"), "role": role})

        if tool_name == "get_current_datetime":
            payload.setdefault("timezone", "Asia/Shanghai")
            return payload

        if tool_name in {"query_attendance_summary", "manage_company_calendar"}:
            date_payload = self._resolve_relative_date_payload(state, role)
            payload = {**date_payload, **payload}

        if tool_name == "query_attendance_summary":
            payload.setdefault("department", "all")
            payload.setdefault("group_by", "department")
        elif tool_name == "manage_company_calendar":
            action = str(payload.get("action") or self._infer_calendar_action(question)).lower()
            payload["action"] = action
            payload.setdefault("event_type", "all")
            payload.setdefault("department", "all")
            if action == "create":
                payload.setdefault("title", self._infer_calendar_title(question))
                payload.setdefault("type", self._infer_calendar_type(question))
                payload.setdefault("time", self._infer_calendar_time(question))
                payload.setdefault("location", "")
                payload.setdefault("description", question)
                if "date" not in payload:
                    create_date = self._infer_calendar_create_date(question, date_payload)
                    if create_date:
                        payload["date"] = create_date
        return payload

    def _resolve_relative_date_payload(self, state: AgentState, role: str) -> dict[str, Any]:
        question = state.get("question", "")
        range_key = self._infer_range_key(question)
        if not range_key:
            return {}
        assert_tool_permission(role, "get_current_datetime", role_policies=self.auth_store.list_role_policies())
        datetime_payload = {"timezone": "Asia/Shanghai"}
        datetime_result = get_current_datetime(datetime_payload)
        ranges = datetime_result.get("ranges") or {}
        selected_range = ranges.get(range_key) or {}
        state.setdefault("tool_calls", []).append(
            {"tool_name": "get_current_datetime", "args": datetime_payload, "ok": True, "risk_level": "low", "purpose": "resolve_relative_date"}
        )
        state.setdefault("observations", []).append({"type": "tool", "tool_name": "get_current_datetime", "result": datetime_result})
        state.setdefault("audit_events", []).append(
            {"event": "tool_call", "tool_name": "get_current_datetime", "role": role, "decision": "allowed"}
        )
        if selected_range:
            return {"start_date": selected_range.get("start_date"), "end_date": selected_range.get("end_date"), "_relative_range": range_key}
        return {}

    @staticmethod
    def _infer_range_key(query: str) -> str | None:
        q = str(query or "")
        checks = [
            ("上个月", "last_month"),
            ("下个月", "next_month"),
            ("这个月", "this_month"),
            ("本月", "this_month"),
            ("上周", "last_week"),
            ("下周", "next_week"),
            ("本周", "this_week"),
            ("这周", "this_week"),
            ("昨天", "yesterday"),
            ("明天", "tomorrow"),
            ("今天", "today"),
            ("当前日期", "today"),
            ("现在", "today"),
        ]
        for keyword, range_key in checks:
            if keyword in q:
                return range_key
        return None

    @staticmethod
    def _infer_calendar_action(query: str) -> str:
        q = str(query or "")
        if any(word in q for word in ["删除", "取消", "移除"]):
            return "delete"
        if any(word in q for word in ["修改", "更新", "调整", "改到", "改成"]):
            return "update"
        if any(word in q for word in ["添加", "新增", "创建", "安排", "加一个"]):
            return "create"
        return "query"

    @staticmethod
    def _infer_calendar_type(query: str) -> str:
        q = str(query or "")
        if "培训" in q:
            return "training"
        if "工资" in q or "发薪" in q:
            return "payday"
        if "节假日" in q or "放假" in q:
            return "holiday"
        if "会议" in q or "周会" in q:
            return "meeting"
        return "event"

    @staticmethod
    def _infer_calendar_time(query: str) -> str:
        q = str(query or "")
        if "下午两点" in q or "下午2点" in q:
            return "14:00-15:00"
        if "上午十点" in q or "上午10点" in q:
            return "10:00-11:00"
        return "全天"

    @staticmethod
    def _infer_calendar_title(query: str) -> str:
        q = str(query or "").strip()
        for marker in ["的", "：", ":"]:
            if marker in q and len(q.rsplit(marker, 1)[-1].strip()) >= 2:
                return q.rsplit(marker, 1)[-1].strip(" 。")
        if "培训" in q:
            return "新员工培训" if "新员工" in q else "培训"
        if "会议" in q:
            return "公司会议"
        return q[:30] or "公司日程"

    @staticmethod
    def _infer_calendar_create_date(query: str, date_payload: dict[str, Any]) -> str | None:
        q = str(query or "")
        weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
        target_weekday = None
        for label, index in weekday_map.items():
            if f"周{label}" in q or f"星期{label}" in q:
                target_weekday = index
                break
        if target_weekday is None:
            return date_payload.get("start_date")
        if not date_payload.get("start_date"):
            return None
        start = date.fromisoformat(str(date_payload.get("start_date")))
        return (start + timedelta(days=target_weekday)).isoformat()

    @staticmethod
    def _format_tool_result(tool_name: str, result: dict[str, Any]) -> str:
        if result.get("error"):
            return f"工具调用失败：{result.get('error')}"
        if tool_name == "get_current_datetime":
            return f"当前日期：{result.get('current_date')}，时间：{result.get('current_time')}，星期：{result.get('weekday')}，时区：{result.get('timezone')}。"
        if tool_name == "query_attendance_summary":
            summary = result.get("summary") or {}
            return (
                f"{result.get('start_date')} 至 {result.get('end_date')} 的考勤汇总："
                f"记录 {summary.get('total_records', 0)} 条，出勤 {summary.get('present', 0)}，"
                f"迟到 {summary.get('late', 0)}，请假 {summary.get('leave', 0)}，缺勤 {summary.get('absent', 0)}，"
                f"出勤率 {summary.get('attendance_rate', '0.00%')}，迟到率 {summary.get('late_rate', '0.00%')}。"
            )
        if tool_name == "manage_company_calendar":
            action = result.get("action")
            if action == "query":
                events = result.get("events") or []
                if not events:
                    return f"{result.get('start_date')} 至 {result.get('end_date')} 暂无公司日程。"
                lines = [f"{result.get('start_date')} 至 {result.get('end_date')} 的公司日程："]
                for event in events:
                    lines.append(f"- {event.get('date')} {event.get('time')} {event.get('title')}（{event.get('location') or '未指定地点'}）")
                return "\n".join(lines)
            return str(result.get("message") or f"公司日程已{result.get('status', '处理')}")
        return str(result)

    def _get_retriever(self) -> Any:
        if self.retriever is None:
            from mini_rag.retrieval.retriever import KnowledgeBaseRetriever

            self.retriever = KnowledgeBaseRetriever(self.settings)
        return self.retriever

    def _invoke_text(
        self,
        state: AgentState,
        node: str,
        system: str,
        user: str,
        llm: Any | None = None,
        model_name: str | None = None,
    ) -> str:
        start = time.perf_counter()
        message = (llm or self.control_llm).invoke([("system", system), ("user", user)])
        content = get_message_content(message)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        state.setdefault("llm_calls", []).append(
            {
                "node": node,
                "model": model_name or self.settings.qwen_control_model or self.settings.qwen_chat_model,
                "prompt_chars": len(system) + len(user),
                "output_chars": len(content),
                "latency_ms": elapsed_ms,
            }
        )
        return content

    def _invoke_json(self, state: AgentState, node: str, system: str, user: str, default: dict[str, Any]) -> dict[str, Any]:
        raw = self._invoke_text(state=state, node=node, system=system, user=user, llm=self.control_llm)
        payload = safe_json_loads(raw, default=default)
        if not isinstance(payload, dict):
            return default
        return payload

    @staticmethod
    def _normalize_query_key(query: str) -> str:
        return " ".join(str(query or "").strip().split()).lower()

    @staticmethod
    def _is_dangerous_question(question: str, standalone_query: str) -> bool:
        text = f"{question} {standalone_query}".lower()
        risky_terms = ["api key", "apikey", "secret", "密钥", "泄露", "密码", "token"]
        return any(term in text for term in risky_terms)

    def _can_skip_reflection(self, state: AgentState) -> bool:
        if state.get("route") != "rag":
            return False
        if int(state.get("reflect_round") or 0) > 0 and state.get("retrieval_made_progress") is False:
            state["skipped_reflection_reason"] = "followup_retrieval_no_new_evidence"
            state.setdefault("evidence_assessment", {})
            state["evidence_assessment"].update(
                {
                    "can_answer_partial": bool(state.get("retrieved_docs")),
                    "followup_tasks": [],
                    "stop_reason": "followup_retrieval_no_new_evidence",
                    "reason": "补检索没有新增有效证据，继续检索收益低，进入回答阶段。",
                }
            )
            state["pending_search_tasks"] = []
            state.setdefault("observations", []).append(
                {"type": "evidence_reflection_skipped", "reason": state["skipped_reflection_reason"]}
            )
            return True
        if state.get("reflect_round"):
            return False
        docs = state.get("retrieved_docs") or []
        if not docs:
            return False
        executed_queries = state.get("executed_queries") or []
        task_count = len(state.get("search_tasks") or [])
        complex_multi_entity = (
            state.get("intent") in {"rag_explain", "rag_compare"}
            and len(state.get("entities") or []) > 1
        )
        if complex_multi_entity:
            return False
        if len(executed_queries) <= 1 and task_count <= 1:
            state["skipped_reflection_reason"] = "single_query_has_evidence"
            state["evidence_assessment"] = {
                "is_sufficient": True,
                "can_answer_partial": False,
                "missing_information": [],
                "followup_tasks": [],
                "reason": "单 query 已召回证据，跳过 LLM 证据反思以减少低价值耗时。",
            }
            state.setdefault("observations", []).append(
                {"type": "evidence_reflection_skipped", "reason": state["skipped_reflection_reason"]}
            )
            return True
        return False

    def _should_use_lightweight_memory(self, state: AgentState) -> bool:
        history = state.get("history") or []
        answer = state.get("final_answer", "")
        if state.get("route") == "direct":
            return True
        return len(history) < max(1, int(self.settings.session_max_turns or 1)) and len(answer) <= 2000

    def _optimize_search_tasks(self, state: AgentState, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Guard retrieval planning quality.

        ``understand_query`` already produces a complete ``standalone_query``.
        Therefore the planning node must not broaden or rewrite the meaning
        again. For normal questions we use the standalone query directly. Only
        when the question is explicitly a comparison/multi-object request do we
        allow a few entity-specific tasks, and even then each task must stay
        anchored to the standalone query.
        """

        standalone_query = self._normalize_query_text(str(state.get("standalone_query") or state.get("question") or ""))
        entities = [str(x).strip() for x in state.get("entities", []) if str(x).strip()]
        intent = str(state.get("intent") or "")
        allow_split = intent in {"rag_compare", "rag_explain"} and len(entities) > 1

        optimized: list[dict[str, Any]] = []
        if not allow_split:
            optimized = [{"query": standalone_query, "purpose": "answer_question", "target_entity": None}]
        else:
            # Keep entity tasks narrow. Do not add new dimensions like “原理/优势/案例”
            # unless those words already appear in the standalone query.
            for task in tasks:
                query = self._normalize_query_text(str(task.get("query") or ""))
                target = str(task.get("target_entity") or "").strip() or None
                if not query:
                    continue
                # If the model generated an over-expanded query, fall back to
                # "standalone_query + target entity" instead of trusting it.
                if target and target not in query:
                    query = f"{standalone_query} {target}"
                if len(query) > max(len(standalone_query) + 40, 80):
                    query = f"{standalone_query} {target or ''}".strip()
                optimized.append({"query": query, "purpose": str(task.get("purpose") or "search"), "target_entity": target})
            if not optimized:
                optimized = [{"query": standalone_query, "purpose": "answer_question", "target_entity": None}]

        for task in optimized:
            task["query"] = self._normalize_query_text(str(task.get("query") or standalone_query))
            task.setdefault("top_k", self.settings.top_k)
            task.setdefault("candidate_k", self.settings.candidate_k)

        max_tasks = max(1, int(getattr(self.settings, "agent_max_search_tasks", 3) or 3))
        return dedupe_keep_order(optimized, key=lambda task: str(task.get("query")))[:max_tasks]

    @staticmethod
    def _normalize_query_text(query: str) -> str:
        return " ".join(str(query or "").strip().split())

    @staticmethod
    def _normalize_tasks(value: Any, fallback_query: str) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        for item in coerce_list(value):
            if isinstance(item, str):
                item = {"query": item, "purpose": "search", "target_entity": None}
            if not isinstance(item, dict):
                continue
            query = str(item.get("query") or "").strip()
            if not query:
                continue
            task = {
                "query": query,
                "purpose": str(item.get("purpose") or "search"),
                "target_entity": item.get("target_entity"),
            }
            for opt_key in ("top_k", "candidate_k", "enable_rerank"):
                if opt_key in item:
                    task[opt_key] = item.get(opt_key)
            tasks.append(task)
        if not tasks and fallback_query:
            tasks = [{"query": fallback_query, "purpose": "answer_question", "target_entity": None}]
        return dedupe_keep_order(tasks, key=lambda task: str(task.get("query")))

    @staticmethod
    def _turn_to_history_item(turn: Any) -> dict[str, Any]:
        answer = getattr(turn, "memory_answer", "") or strip_citations_and_metadata(getattr(turn, "answer", ""))
        return {
            "question": getattr(turn, "question", ""),
            "standalone_query": getattr(turn, "standalone_query", ""),
            "answer": getattr(turn, "answer", ""),
            "memory_answer": answer,
            "intent": getattr(turn, "intent", ""),
            "topic": getattr(turn, "topic", ""),
            "entities": getattr(turn, "entities", []),
            "created_at": getattr(turn, "created_at", 0.0),
        }


def create_initial_state(
    question: str,
    session_id: str | None = None,
    retrieval_mode: str | None = None,
    enable_rerank: bool | None = None,
    user_id: str | None = None,
    role: str | None = None,
    trace_id: str | None = None,
    kb_ids: list[str] | None = None,
) -> AgentState:
    workflow_run_id = uuid4().hex
    return {
        "question": question,
        "user_query": question,
        "session_id": session_id,
        "user_id": user_id or "anonymous",
        "role": normalize_role(role),
        "workflow_run_id": workflow_run_id,
        "trace_id": trace_id or workflow_run_id,
        "retrieval_mode": retrieval_mode,
        "enable_rerank": enable_rerank,
        "requested_kbs": kb_ids or [],
        "allowed_kbs": [],
        "used_kbs": [],
        "conversation_summary": "",
        "history": [],
        "intent": "",
        "route": "direct",
        "risk_level": "low",
        "standalone_query": question,
        "topic": "",
        "entities": [],
        "required_tools": [],
        "selected_tool": None,
        "tool_input": {},
        "search_tasks": [],
        "pending_search_tasks": [],
        "executed_queries": [],
        "_executed_query_keys": [],
        "_retrieval_cache": {},
        "retrieved_docs": [],
        "sources": [],
        "evidence_brief": "",
        "observations": [],
        "tool_calls": [],
        "evidence_assessment": {},
        "reflect_round": 0,
        "final_answer": "",
        "memory_update": {},
        "node_trace": [],
        "llm_calls": [],
        "audit_events": [],
        "skipped_reflection_reason": None,
        "error": None,
    }
