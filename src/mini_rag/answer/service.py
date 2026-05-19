from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

from mini_rag.answer.composer import compose_template_answer
from mini_rag.answer.packet import build_answer_packet
from mini_rag.answer.policy_router import route_answer_policy
from mini_rag.capabilities.rag.formatter import sources_to_evidence_text
from mini_rag.capabilities.rag.verifier import RagAnswerabilityGate
from mini_rag.config import Settings
from mini_rag.graph.prompts import GENERATE_ANSWER_SYSTEM, format_answer_user
from mini_rag.graph.utils import compact_evidence_text, get_message_content

InvokeText = Callable[..., str]
AppendLLMCallTrace = Callable[..., dict[str, Any]]
RoleAllowedActions = Callable[[dict[str, Any]], dict[str, list[str]]]


def _compact_answer_packet(packet: Any) -> dict[str, Any]:
    return {
        "route": packet.route,
        "status": packet.status,
        "messages": list(packet.messages),
        "task_results": list(packet.task_results),
        "sources": list(packet.sources),
        "should_call_llm": packet.should_call_llm,
    }


def _rag_task_titles(state: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for result in state.get("task_results") or []:
        if not isinstance(result, dict) or str(result.get("kind") or "").lower() != "rag":
            continue
        title = str(result.get("objective") or result.get("query") or "知识库问题").strip()
        if title and title not in titles:
            titles.append(title)
    return titles


def _tool_template_answer(state: dict[str, Any]) -> str:
    tool_results = [
        result
        for result in (state.get("task_results") or [])
        if isinstance(result, dict) and str(result.get("kind") or "").lower() == "tool"
    ]
    if not tool_results:
        return ""
    tool_state = dict(state)
    tool_state["route"] = "tool"
    tool_state["task_results"] = tool_results
    return compose_template_answer(tool_state) or ""


def _must_preserve_locked_fact(state: dict[str, Any], locked_fact: str) -> bool:
    if not locked_fact:
        return False
    route = str(state.get("route") or "")
    intent = str(state.get("intent") or "")
    if route == "reject" or intent in {"permission_required", "need_clarification", "clarification_required"}:
        return True
    assessment = state.get("rag_answerability") or {}
    if assessment.get("answerable") is False or assessment.get("mode") == "partial":
        return True
    text = f"{state.get('question') or ''}\n{state.get('standalone_query') or ''}".lower()
    return "event_id" in text and any(token in text for token in ("event_id=all", "event_id = all", "event_id=multiple", "event_id_from"))


def _answer_preserves_locked_fact(answer: str, locked_fact: str) -> bool:
    if not locked_fact:
        return True
    answer = str(answer or "")
    if not answer:
        return False
    anchors = [
        "不能",
        "无权",
        "没有权限",
        "需要",
        "澄清",
        "当前可访问知识库未找到明确依据",
        "知识库子问题缺少明确依据",
        "证据不足",
        "没有匹配",
    ]
    return any(anchor in answer for anchor in anchors if anchor in locked_fact)


def _has_permission_block(state: dict[str, Any]) -> bool:
    for event in (state.get("audit_events") or []) + (state.get("observations") or []):
        if not isinstance(event, dict):
            continue
        if "permission" in str(event.get("event") or event.get("type") or "") and str(event.get("status") or event.get("decision") or "") == "blocked":
            return True
    return False


class AnswerService:
    """Compose final answers from compact packets and evidence gates."""

    def __init__(
        self,
        *,
        settings: Settings,
        invoke_text: InvokeText,
        append_llm_call_trace: AppendLLMCallTrace,
        role_allowed_actions: RoleAllowedActions,
        answer_llm: Any,
    ) -> None:
        self.settings = settings
        self.invoke_text = invoke_text
        self.append_llm_call_trace = append_llm_call_trace
        self.role_allowed_actions = role_allowed_actions
        self.answer_llm = answer_llm
        self.rag_answerability_gate = RagAnswerabilityGate()

    def _apply_answerability_gate(self, state: dict[str, Any], policy_strategy: str) -> str | None:
        has_rag_result = any(
            isinstance(result, dict) and str(result.get("kind") or "").lower() == "rag"
            for result in (state.get("task_results") or [])
        )
        if not has_rag_result and str(state.get("route") or "") != "rag":
            return None
        report = self.rag_answerability_gate.evaluate(state)
        state["rag_answerability"] = report.to_dict()
        if report.answerable:
            if getattr(report, "mode", "") == "partial" and getattr(report, "unsupported_task_ids", ()):  # keep non-RAG facts locked
                template_answer = _tool_template_answer(state)
                if template_answer:
                    rag_targets = "、".join(_rag_task_titles(state)) or "知识库部分"
                    message = report.message or "当前可访问知识库未找到明确依据。"
                    if "当前可访问知识库未找到明确依据" not in message:
                        message = f"当前可访问知识库未找到明确依据；{message}"
                    evidence_notice = f"关于{rag_targets}：{message}"
                    return f"{template_answer}\n\n{evidence_notice}"
            return None
        state.setdefault("observations", []).append(
            {
                "type": "rag_answerability_gate",
                "status": "blocked",
                "summary": report.message or "当前可访问知识库未找到明确依据。",
            }
        )

        if policy_strategy == "rag_grounded":
            return report.message or "当前可访问知识库未找到明确依据，不能可靠回答该问题。"

        template_answer = _tool_template_answer(state) or compose_template_answer(state)
        rag_targets = "、".join(_rag_task_titles(state)) or "知识库部分"
        evidence_notice = f"关于{rag_targets}：{report.message or '当前可访问知识库未找到明确依据。'}"
        if template_answer:
            return f"{template_answer}\n\n{evidence_notice}"
        return evidence_notice

    def _build_user_prompt(self, state: dict[str, Any]) -> str:
        answer_packet = build_answer_packet(state)
        compact_packet = _compact_answer_packet(answer_packet)
        compact_packet["answer_question"] = str(state.get("question") or state.get("standalone_query") or "")
        state["answer_packet"] = compact_packet
        supporting_sources = [item for item in (state.get("sources") or state.get("supporting_sources") or []) if isinstance(item, dict)]
        evidence_text = state.get("supporting_evidence_brief") or sources_to_evidence_text(supporting_sources)
        has_rag_result = any(
            isinstance(result, dict) and str(result.get("kind") or "").lower() == "rag"
            for result in (state.get("task_results") or [])
        )
        if has_rag_result and not supporting_sources:
            evidence_text = "当前可访问知识库未找到明确支持证据。"
        elif not has_rag_result and not evidence_text:
            evidence_text = compact_evidence_text(
                state.get("retrieved_docs", []), entities=state.get("entities", [])
            )
        return format_answer_user(
            question=state.get("question", ""),
            standalone_query=state.get("standalone_query", state.get("question", "")),
            route=state.get("route", "direct"),
            model_name=self.settings.answer_model or self.settings.qwen_chat_model,
            evidence_assessment=state.get("rag_answerability", {}),
            evidence_text=evidence_text,
            selected_tool=None,
            tool_input={},
            tool_result={},
            current_tool_context={},
            execution_plan=state.get("execution_plan", {}),
            task_results=list(answer_packet.task_results),
            completion_assessment=state.get("completion_assessment", {}),
            role_allowed_actions=self.role_allowed_actions(state),
        )

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        policy = route_answer_policy(state)
        state["answer_policy"] = {"strategy": policy.strategy, "should_call_llm": policy.should_call_llm, "reason": policy.reason}
        locked_fact = compose_template_answer(state) or str(state.get("final_answer") or "")
        if locked_fact:
            state["final_answer"] = locked_fact
        gated_answer = None if policy.strategy == "safety_llm" else self._apply_answerability_gate(state, policy.strategy)
        if gated_answer:
            # Locked fact for the Answer LLM. The final wording still goes
            # through the unified answer model, but the model may not override
            # this insufficiency decision.
            state["final_answer"] = gated_answer
            locked_fact = gated_answer

        user_prompt = self._build_user_prompt(state)
        answer = self.invoke_text(
            state=state,
            node="generate_answer",
            system=GENERATE_ANSWER_SYSTEM,
            user=user_prompt,
            llm=self.answer_llm,
            model_name=self.settings.answer_model or self.settings.qwen_chat_model,
        )
        answer = answer.strip()
        if _must_preserve_locked_fact(state, locked_fact) and not _answer_preserves_locked_fact(answer, locked_fact):
            answer = locked_fact
        permission_wording_needed = (
            _has_permission_block(state)
            or str(state.get("intent") or "") == "permission_required"
        )
        if permission_wording_needed and "无权" not in answer:
            answer = f"{answer}\n\n因此你无权执行该写操作。".strip()
        state["final_answer"] = answer or locked_fact or "抱歉，我暂时无法生成回答。"
        return state

    def stream(self, state: dict[str, Any]) -> Iterator[str]:
        policy = route_answer_policy(state)
        state["answer_policy"] = {"strategy": policy.strategy, "should_call_llm": policy.should_call_llm, "reason": policy.reason}
        locked_fact = compose_template_answer(state) or str(state.get("final_answer") or "")
        if locked_fact:
            state["final_answer"] = locked_fact
        gated_answer = None if policy.strategy == "safety_llm" else self._apply_answerability_gate(state, policy.strategy)
        if gated_answer:
            state["final_answer"] = gated_answer
            locked_fact = gated_answer

        user_prompt = self._build_user_prompt(state)
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
            self.append_llm_call_trace(
                state,
                node="generate_answer",
                model=self.settings.answer_model or self.settings.qwen_chat_model,
                system=GENERATE_ANSWER_SYSTEM,
                user=user_prompt,
                output=answer,
                latency_ms=elapsed_ms,
                streaming=True,
            )
        else:
            answer = self.invoke_text(
                state=state,
                node="generate_answer",
                system=GENERATE_ANSWER_SYSTEM,
                user=user_prompt,
                llm=llm,
                model_name=self.settings.answer_model or self.settings.qwen_chat_model,
            ).strip()
            if answer:
                yield answer
        if _must_preserve_locked_fact(state, locked_fact) and not _answer_preserves_locked_fact(answer, locked_fact):
            answer = locked_fact
        state["final_answer"] = answer or locked_fact or "抱歉，我暂时无法生成回答。"


__all__ = ["AnswerService"]
