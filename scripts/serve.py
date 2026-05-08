from __future__ import annotations

from pathlib import Path
import sys

# 允许你在没有 pip install -e . 的情况下直接运行脚本。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import uvicorn


if __name__ == "__main__":
    uvicorn.run("mini_rag.api.app:app", host="127.0.0.1", port=8000, reload=True)
