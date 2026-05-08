from __future__ import annotations

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mini_rag.config import get_settings
from mini_rag.evaluation.retrieval_ablation import run_retrieval_ablation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run retrieval ablation: vector vs hybrid vs hybrid+rerank")
    parser.add_argument("--questions", default=None, help="Optional JSONL question file. Defaults to EVAL_QUESTIONS_PATH.")
    args = parser.parse_args()
    report = run_retrieval_ablation(get_settings(), questions_path=args.questions)
    print("Retrieval ablation finished:")
    for item in report["modes"]:
        print(item["mode"], item["metrics"])
    print("JSON:", report["output_json_path"])
    print("Markdown:", report["output_md_path"])
