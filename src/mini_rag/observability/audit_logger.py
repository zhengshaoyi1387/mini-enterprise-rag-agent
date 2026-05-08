from __future__ import annotations

"""Append-only audit log for enterprise Agent demos.

Trace is for debugging the Agent execution path. Audit is for answering: who did
what, which knowledge bases were requested, which tools were called, and whether
permission checks blocked the operation.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mini_rag.config import Settings


def write_audit_event(settings: Settings, event: dict[str, Any]) -> None:
    path = settings.audit_log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"time": datetime.now(timezone.utc).isoformat(), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_recent_audit_events(settings: Settings, limit: int = 50) -> list[dict[str, Any]]:
    path = settings.audit_log_path
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]
    items: list[dict[str, Any]] = []
    for line in lines:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items
