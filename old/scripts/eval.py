from __future__ import annotations

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mini_rag.config import get_settings
from mini_rag.eval import run_eval


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run lightweight RAG eval")
    parser.add_argument("--questions", default=None, help="Optional JSONL question file. Defaults to EVAL_QUESTIONS_PATH.")
    args = parser.parse_args()
    report = run_eval(get_settings(), questions_path=args.questions)
    print("评测完成：")
    print(
        {
            "question_count": report["question_count"],
            "recall_at_k": report["recall_at_k"],
            "citation_hit_rate": report["citation_hit_rate"],
            "refusal_hit_rate": report["refusal_hit_rate"],
            "avg_latency_ms": report["avg_latency_ms"],
            "p95_latency_ms": report["p95_latency_ms"],
            "output_path": report["output_path"],
            "output_md_path": report["output_md_path"],
        }
    )
