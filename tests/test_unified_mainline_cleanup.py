from __future__ import annotations

from pathlib import Path


def test_plain_rag_branch_is_removed_from_active_source() -> None:
    active_files = [path for path in Path("src").rglob("*.py") if "__pycache__" not in path.parts]
    text = "\n".join(path.read_text(encoding="utf-8") for path in active_files)

    forbidden = [
        "RAG" + "Question" + "Answerer",
        "get_" + "rag_" + "chain",
        "_RAG" + "_INSTANCE",
        "USE" + "_AGENT",
        "select_" + "daily_" + "tool_" + "by_" + "rule",
    ]
    for item in forbidden:
        assert item not in text


def test_graph_nodes_exposes_only_current_runtime_boundary() -> None:
    source = Path("src/mini_rag/graph/nodes.py").read_text(encoding="utf-8")

    assert "from mini_rag.orchestration.agentic_nodes import AgenticRAGNodes" in source
    assert "get_current_datetime" not in source


def test_rag_verifier_has_no_keyword_rule_gate() -> None:
    source = Path("src/mini_rag/capabilities/rag/verifier.py").read_text(encoding="utf-8")

    for forbidden in [
        "STOP" + "_TERMS",
        "SYNONYM" + "_GROUPS",
        "POLICY" + "_MARKERS",
        "Evidence" + "Relevance" + "Verifier",
        "is_" + "supporting_" + "source",
        "extract_" + "relevance_" + "terms",
    ]:
        assert forbidden not in source
