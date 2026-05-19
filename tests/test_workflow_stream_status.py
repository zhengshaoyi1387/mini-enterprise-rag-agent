from __future__ import annotations

from mini_rag.graph.workflow import AgenticRAGWorkflow


class _FakeNodes:
    def build_runtime_context(self, state):
        state["visited"] = ["build_runtime_context"]
        return state

    def plan_with_llm(self, state):
        state["visited"].append("plan_with_llm")
        return state

    def resolve_plan_time(self, state):
        state["visited"].append("resolve_plan_time")
        return state

    def validate_plan(self, state):
        state["visited"].append("validate_plan")
        return state

    def react_execute(self, state):
        state["visited"].append("react_execute")
        state["route"] = "direct"
        state["sources"] = []
        return state

    def stream_generate_answer(self, state):
        state["visited"].append("answer_with_llm")
        state["final_answer"] = "ok"
        yield "ok"

    def update_memory(self, state):
        state["visited"].append("update_memory")
        return state

    def build_trace(self, state):
        return {"answer": state.get("final_answer"), "visited": state["visited"]}


def test_workflow_stream_emits_mainline_status_events_before_tokens() -> None:
    workflow = AgenticRAGWorkflow.__new__(AgenticRAGWorkflow)
    workflow.nodes = _FakeNodes()

    events = list(workflow.stream("你好", user_id="u1", role="employee", kb_ids=["public"]))
    status_stages = [event["stage"] for event in events if event.get("event") == "status"]

    assert status_stages == [
        "runtime_context",
        "plan_with_llm",
        "resolve_plan_time",
        "validate_plan",
        "react_execute",
        "answer_with_llm",
        "update_memory",
    ]
    event_names = [event["event"] for event in events]
    answer_status_index = next(
        index
        for index, event in enumerate(events)
        if event.get("event") == "status" and event.get("stage") == "answer_with_llm"
    )
    assert event_names.index("token") > answer_status_index
    assert event_names[-1] == "final"
