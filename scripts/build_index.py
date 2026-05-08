from __future__ import annotations

import argparse
from pathlib import Path
import sys

# 允许你在没有 pip install -e . 的情况下直接运行脚本。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mini_rag.config import get_settings
from mini_rag.ingestion.build_index import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="构建企业知识库 Chroma 向量索引")
    parser.add_argument("--reset", action="store_true", help="删除旧索引后重新构建")
    args = parser.parse_args()

    settings = get_settings()
    result = build_index(settings, reset=args.reset)
    print("索引构建完成：")
    print(result)


if __name__ == "__main__":
    main()
