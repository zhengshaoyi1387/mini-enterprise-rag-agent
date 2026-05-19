from __future__ import annotations

from pathlib import Path


def test_graph_planning_contract_is_thin_facade() -> None:
    path = Path("src/mini_rag/graph/planning_contract.py")
    source = path.read_text(encoding="utf-8")

    assert len(source.splitlines()) < 120
    assert "mini_rag.capabilities.calendar" not in source
    assert "mini_rag.capabilities.attendance" not in source
    assert "class PlanningContractNormalizer" not in source
