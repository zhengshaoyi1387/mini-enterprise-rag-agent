from __future__ import annotations

from typing import Any

from mini_rag.config import Settings


class TraceBuilder:
    """Build compact runtime traces and LLM-call trace entries."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def trace_llm_text(self, value: str) -> str:
        text = str(value or "")
        max_chars = int(getattr(self.settings, "trace_llm_io_max_chars", 0) or 0)
        if max_chars > 0 and len(text) > max_chars:
            return text[:max_chars] + f"\n...[truncated {len(text) - max_chars} chars]"
        return text

    def build_llm_call_trace(
        self,
        *,
        node: str,
        model: str,
        system: str,
        user: str,
        output: str,
        latency_ms: float,
        streaming: bool = False,
    ) -> dict[str, Any]:
        call: dict[str, Any] = {
            "node": node,
            "model": model,
            "prompt_chars": len(system) + len(user),
            "output_chars": len(output),
            "latency_ms": latency_ms,
        }
        if streaming:
            call["streaming"] = True
        if bool(getattr(self.settings, "trace_llm_io", True)):
            call["input"] = {
                "messages": [
                    {"role": "system", "content": self.trace_llm_text(system)},
                    {"role": "user", "content": self.trace_llm_text(user)},
                ]
            }
            call["output"] = {"content": self.trace_llm_text(output)}
        return call

    def append_llm_call_trace(
        self,
        state: dict[str, Any],
        *,
        node: str,
        model: str,
        system: str,
        user: str,
        output: str,
        latency_ms: float,
        streaming: bool = False,
    ) -> dict[str, Any]:
        call = self.build_llm_call_trace(
            node=node,
            model=model,
            system=system,
            user=user,
            output=output,
            latency_ms=latency_ms,
            streaming=streaming,
        )
        state.setdefault("llm_calls", []).append(call)
        return call

    def build_trace(self, state: dict[str, Any]) -> dict[str, Any]:
        assessment = state.get("completion_assessment") or {}
        total_latency_ms = round(sum(float(item.get("latency_ms") or 0) for item in state.get("node_trace", []) if isinstance(item, dict)), 2)
        trace = {
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
            "message_type": state.get("message_type"),
            "context_usage": state.get("context_usage"),
            "goals": state.get("goals", []),
            "goal_coverage": state.get("goal_coverage", {}),
            "goal_contract": state.get("goal_contract", {}),
            "completion_check": state.get("completion_check", {}),
            "completion_checks": state.get("completion_checks", []),
            "time_requirement": state.get("time_requirement", {}),
            "knowledge_requirement": state.get("knowledge_requirement", {}),
            "execution_plan": state.get("execution_plan", {}),
            "task_results": state.get("task_results", []),
            "completed_tasks": state.get("completed_tasks", []),
            "plan_validation": state.get("plan_validation", {}),
            "risk_level": state.get("risk_level"),
            "standalone_query": state.get("standalone_query"),
            "topic": state.get("topic"),
            "entities": state.get("entities", []),
            "search_tasks": state.get("search_tasks", []),
            "executed_queries": state.get("executed_queries", []),
            "evidence_brief_chars": len(state.get("evidence_brief", "") or ""),
            "skipped_reflection_reason": state.get("skipped_reflection_reason"),
            "react_status": state.get("react_status", ""),
            "react_steps": state.get("react_steps", []),
            "rag_latency_summary": state.get("rag_latency_summary", {}),
            "answer_policy": state.get("answer_policy", {}),
            "node_trace": state.get("node_trace", []),
            "mainline_log": state.get("mainline_log", []),
            "mainline_log_text": state.get("mainline_log_text", ""),
            "llm_calls": state.get("llm_calls", []),
            "llm_trace_config": {
                "io_enabled": bool(getattr(self.settings, "trace_llm_io", True)),
                "io_max_chars": int(getattr(self.settings, "trace_llm_io_max_chars", 0) or 0),
            },
            "total_latency_ms": total_latency_ms,
            "candidate_tool": state.get("candidate_tool"),
            "previous_tool_context": state.get("previous_tool_context", {}),
            "current_tool_context": state.get("current_tool_context", {}),
            "time_reference": state.get("time_reference", {}),
            "needs_time_resolution": state.get("needs_time_resolution", False),
            "relative_time": state.get("relative_time"),
            "time_context_result": state.get("time_context_result", {}),
            "runtime_context": state.get("runtime_context", {}),
            "plan_state": state.get("plan_state", {}),
            "execution_state": state.get("execution_state", {}),
            "answer_state": state.get("answer_state", {}),
            "missing_required_slots": state.get("missing_required_slots", []),
            "tool_calls": state.get("tool_calls", []),
            "observations": state.get("observations", []),
            "audit_events": state.get("audit_events", []),
            "sources": state.get("sources", []),
            "candidate_sources": state.get("candidate_sources", []),
            "answer": state.get("final_answer", ""),
            "error": state.get("error"),
        }
        if isinstance(assessment, dict):
            trace["completion_control"] = {
                "ready_to_answer": bool(assessment.get("ready_to_answer")),
                "next_action": assessment.get("next_action"),
                "followup_count": len(assessment.get("followup_tasks") or []),
                "missing_count": len(assessment.get("missing_objectives") or []),
                "status": assessment.get("status"),
                "goal_type": assessment.get("goal_type"),
            }
        return trace
