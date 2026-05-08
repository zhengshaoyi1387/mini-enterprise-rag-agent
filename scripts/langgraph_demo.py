from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mini_rag.agent.graph_agent import EnterpriseKnowledgeGraphAgent
from mini_rag.config import get_settings
from mini_rag.observability.trace import save_trace


def main() -> None:
    settings = get_settings()
    agent = EnterpriseKnowledgeGraphAgent(settings)
    result = agent.ask("根据知识库说明智能客服平台有哪些核心模块", session_id="langgraph-demo")
    trace_path = save_trace(settings, result["trace"])
    print("Final Answer:")
    print(result["answer"])
    print("\nRoute:")
    print(result.get("route"))
    print("\nTrace Path:")
    print(trace_path)


if __name__ == "__main__":
    main()
