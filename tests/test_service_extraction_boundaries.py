from __future__ import annotations

from pathlib import Path


def test_new_architecture_service_modules_exist() -> None:
    for path in [
        "src/mini_rag/planning/goal_extractor.py",
        "src/mini_rag/planning/coverage_checker.py",
        "src/mini_rag/orchestration/react_executor.py",
        "src/mini_rag/answer/policy_router.py",
        "src/mini_rag/answer/service.py",
        "src/mini_rag/memory/service.py",
        "src/mini_rag/observability/trace_builder.py",
        "src/mini_rag/capabilities/rag/service.py",
    ]:
        assert Path(path).exists(), path


def test_orchestration_nodes_no_longer_owns_major_service_logic() -> None:
    source = Path("src/mini_rag/orchestration/agentic_nodes.py").read_text(encoding="utf-8")

    assert len(source.splitlines()) < 1500
    assert "ThreadPoolExecutor" not in source
    assert "COMPLETION_REFLECT_SYSTEM" not in source
    assert "MEMORY_UPDATE_SYSTEM" not in source
    assert "def build_trace" in source
    assert "TraceBuilder" in source
