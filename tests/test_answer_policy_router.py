from __future__ import annotations

from mini_rag.answer.policy_router import route_answer_policy


def test_policy_router_sends_pure_tool_results_to_answer_llm() -> None:
    decision = route_answer_policy(
        {
            "route": "tool",
            "task_results": [{"task_id": "calendar", "kind": "tool", "status": "ok"}],
        }
    )

    assert decision.strategy == "tool_llm"
    assert decision.should_call_llm is True


def test_policy_router_uses_grounded_llm_for_pure_rag() -> None:
    decision = route_answer_policy(
        {
            "route": "rag",
            "task_results": [{"task_id": "policy", "kind": "rag", "status": "ok"}],
        }
    )

    assert decision.strategy == "rag_grounded"
    assert decision.should_call_llm is True


def test_policy_router_uses_synthesis_for_react_mixed_packet() -> None:
    decision = route_answer_policy(
        {
            "route": "tool",
            "react_status": "success",
            "task_results": [
                {"task_id": "calendar", "kind": "tool", "status": "ok"},
                {"task_id": "policy", "kind": "rag", "status": "ok"},
            ],
        }
    )

    assert decision.strategy == "synthesis"
    assert decision.should_call_llm is True


def test_policy_router_sends_clarification_and_refusal_to_locked_answer_llm() -> None:
    assert route_answer_policy({"route": "direct", "intent": "need_clarification"}).strategy == "clarification_llm"
    assert route_answer_policy({"route": "direct", "intent": "permission_required"}).strategy == "refusal_llm"
