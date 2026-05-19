from __future__ import annotations

from mini_rag.capabilities.registry import CapabilityRegistry, default_capability_registry


def test_default_capability_registry_exposes_required_contracts() -> None:
    registry = default_capability_registry()

    names = {contract.name for contract in registry.contracts()}

    assert names == {
        "datetime",
        "calendar_query",
        "calendar_write",
        "attendance_query",
        "rag_qa",
        "mixed_task",
    }


def test_registry_contracts_are_permission_and_action_aware() -> None:
    registry = default_capability_registry()

    calendar_write = registry.require("calendar_write")
    attendance = registry.require("attendance_query")
    rag = registry.require("rag_qa")

    assert calendar_write.allowed_roles == ("admin",)
    assert set(calendar_write.write_actions) == {"create", "update", "delete"}
    assert attendance.read_actions == ("query",)
    assert rag.answer_policy


def test_registry_lists_template_capabilities_separately_from_llm_rag() -> None:
    registry = default_capability_registry()

    template_names = {contract.name for contract in registry.template_answer_contracts()}
    llm_names = {contract.name for contract in registry.llm_answer_contracts()}

    assert {"datetime", "calendar_query", "calendar_write", "attendance_query"} <= template_names
    assert "rag_qa" in llm_names
