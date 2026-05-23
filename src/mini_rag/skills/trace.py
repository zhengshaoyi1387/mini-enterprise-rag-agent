from __future__ import annotations

import time
from typing import Any


def now_ms() -> float:
    return time.perf_counter() * 1000


def skill_trace_event(
    skill_name: str,
    phase: str,
    *,
    ok: bool = True,
    latency_ms: float = 0,
    reason: str = "",
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "skill_name": skill_name,
        "phase": phase,
        "ok": bool(ok),
        "latency_ms": round(float(latency_ms or 0), 2),
        "reason": reason,
        "error": error,
    }

