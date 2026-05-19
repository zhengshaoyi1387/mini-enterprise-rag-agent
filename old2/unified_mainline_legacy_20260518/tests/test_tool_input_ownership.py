from __future__ import annotations

from pathlib import Path


def test_tools_input_contract_is_compatibility_shim() -> None:
    source = Path("src/mini_rag/tools/input_contract.py").read_text(encoding="utf-8")

    assert len(source.splitlines()) < 40
    assert "mini_rag.execution.tool_input" in source
    assert "def build_tool_payload" not in source
    assert "CALENDAR_UPDATE_FIELDS" not in source
