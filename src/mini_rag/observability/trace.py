from __future__ import annotations

import re
import time
from pathlib import Path

from mini_rag.config import Settings
from mini_rag.utils import dump_json, ensure_dir, stable_hash


def _safe_trace_id(value: str | None) -> str:
    """Return a filesystem-safe trace id segment."""

    cleaned = re.sub(r"[^a-zA-Z0-9_.-]", "_", value or "")[:80]
    return cleaned or "unknown"


def save_trace(settings: Settings, trace: dict) -> Path | None:
    """保存一次问答 trace。

    trace 的价值：
    - 看 Agent 是否真的调用了工具。
    - 看检索返回了哪些 chunk。
    - 看每个阶段耗时多少。
    - 面试时可以展示你有工程化排查意识。

    P0 改造后，文件名优先包含显式 trace_id，方便 ``GET /traces/{trace_id}``
    直接定位。旧调用如果没有 trace_id，则继续使用问题 hash 兜底，保持兼容。
    """
    if not settings.save_trace:
        return None

    ensure_dir(settings.trace_dir)
    question = str(trace.get("question", "unknown"))
    ts = time.strftime("%Y%m%d_%H%M%S")
    trace_id = _safe_trace_id(trace.get("trace_id"))
    if trace_id == "unknown":
        trace_id = stable_hash(question + ts, length=8)
        trace.setdefault("trace_id", trace_id)
    path = settings.trace_dir / f"agent_trace_{ts}_{trace_id}.json"
    dump_json(path, trace)
    return path
