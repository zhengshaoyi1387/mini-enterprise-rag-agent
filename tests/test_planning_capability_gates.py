from __future__ import annotations

from mini_rag.planning.gates import apply_capability_gates


class FakeToolRegistry:
    def __init__(self, allowed: dict[tuple[str, str], set[str]]):
        self.allowed = allowed

    def has_tool(self, tool: str) -> bool:
        return tool in {"manage_company_calendar", "query_attendance_summary", "get_current_datetime"}

    def allowed_actions(self, tool: str, role: str | None, role_policies=None) -> set[str]:
        return self.allowed.get((tool, str(role or "")), set())


def test_capability_gate_refuses_disallowed_calendar_write_before_execution() -> None:
    payload = {"route": "tool", "selected_tool": "manage_company_calendar", "selected_action": "update"}
    tasks = [
        {
            "task_id": "t1",
            "kind": "tool",
            "tool": "manage_company_calendar",
            "action": "update",
            "tool_input": {"action": "update", "event_id": "EVT-20260518-0001", "title": "新标题"},
        }
    ]

    gated = apply_capability_gates(
        payload,
        tasks,
        role="employee",
        tool_registry=FakeToolRegistry({("manage_company_calendar", "employee"): {"query"}}),
    )

    assert gated is not None
    assert gated["route"] == "direct"
    assert gated["intent"] == "permission_required"
    assert gated["execution_plan"]["tasks"] == []
    assert gated["normalization_reason"] == "task action not visible"


def test_capability_gate_clarifies_calendar_create_missing_required_fields() -> None:
    payload = {"route": "tool", "selected_tool": "manage_company_calendar", "selected_action": "create"}
    tasks = [
        {
            "task_id": "t1",
            "kind": "tool",
            "tool": "manage_company_calendar",
            "action": "create",
            "tool_input": {"action": "create", "title": "公司会议"},
        }
    ]

    gated = apply_capability_gates(
        payload,
        tasks,
        role="admin",
        tool_registry=FakeToolRegistry({("manage_company_calendar", "admin"): {"query", "create", "update", "delete"}}),
    )

    assert gated is not None
    assert gated["route"] == "direct"
    assert gated["intent"] == "need_clarification"
    assert gated["missing_required_slots"] == ["date,time"]
    assert gated["validation_status"] == "needs_clarification"
    assert gated["validation_issues"][0]["code"] == "calendar_create_missing_required_fields"
