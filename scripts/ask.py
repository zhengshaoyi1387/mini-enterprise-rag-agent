from __future__ import annotations

import argparse
from pathlib import Path
import sys

# 允许你在没有 pip install -e . 的情况下直接运行脚本。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mini_rag.agent.agent import EnterpriseKnowledgeAgent
from mini_rag.config import get_settings
from mini_rag.observability.trace import save_trace


def main() -> None:
    parser = argparse.ArgumentParser(description="向企业知识库提问")
    parser.add_argument("question", help="你的问题")
    parser.add_argument("--session-id", default=None, help="多轮会话 ID")
    parser.add_argument("--retrieval-mode", default=None, help="检索模式：hybrid 或 vector")
    parser.add_argument("--no-rerank", action="store_true", help="关闭 Qwen rerank")
    args = parser.parse_args()

    settings = get_settings()

    qa = EnterpriseKnowledgeAgent(settings)
    result = qa.ask(
        args.question,
        session_id=args.session_id,
        retrieval_mode=args.retrieval_mode,
        enable_rerank=False if args.no_rerank else None,
    )
    trace_path = save_trace(settings, result["trace"])

    print("\n答案：")
    print(result["answer"])

    if result.get("sources"):
        print("\n引用来源：")
        for source in result["sources"]:
            print(source)

    if trace_path:
        print(f"\nTrace 已保存：{trace_path}")


if __name__ == "__main__":
    main()
