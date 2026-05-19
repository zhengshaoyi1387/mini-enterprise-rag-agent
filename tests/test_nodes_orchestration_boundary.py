from __future__ import annotations

from pathlib import Path


def test_graph_nodes_is_thin_compatibility_boundary() -> None:
    source = Path("src/mini_rag/graph/nodes.py").read_text(encoding="utf-8")

    assert len(source.splitlines()) < 800
    assert "ThreadPoolExecutor" not in source
    assert "manage_company_calendar" not in source
    assert "query_attendance_summary" not in source
    assert "format_answer_user" not in source
