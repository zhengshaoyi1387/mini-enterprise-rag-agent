from __future__ import annotations

from mini_rag.execution.tool_executor import execute_selected_tool


class FakeRegistry:
    def has_tool(self, name: str) -> bool:
        return name == "known_tool"

    def invoke(self, name: str, payload: dict):
        return {"status": "ok", "tool_name": name, "echo": payload}


def test_tool_executor_blocks_unknown_tool_and_records_result() -> None:
    state = {"selected_tool": "missing_tool", "role": "employee", "tool_calls": [], "audit_events": []}
    recorded: list[int] = []

    execute_selected_tool(
        state,
        tool_registry=FakeRegistry(),
        role_policies=None,
        build_payload=lambda *_args: {},
        verify_tool_result=lambda *_args: None,
        build_current_tool_context=lambda *_args: {},
        record_tool_task_result=lambda _state, before: recorded.append(before),
        friendly_tool_error=lambda *_args, **_kwargs: "",
        friendly_tool_validation_error=lambda *_args: "",
        friendly_permission_answer=lambda *_args: "",
    )

    assert state["tool_result"]["error"] == "unknown tool"
    assert state["final_answer"] == "没有识别到可执行的企业能力。"
    assert state["tool_calls"][0]["reason"] == "unknown tool"
    assert recorded == [0]
