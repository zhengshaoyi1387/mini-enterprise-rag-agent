from __future__ import annotations

from typing import Any


def public_search_task(task: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in task.items() if key != "_plan_task"}


def dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in sources:
        key = str(src.get("chunk_id") or src.get("source") or src.get("title_path") or src)
        if key in seen:
            continue
        seen.add(key)
        out.append(src)
    return out


def dedupe_task_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        key = str(item.get("task_id") or item.get("query") or len(out))
        if key in seen:
            out = [old for old in out if str(old.get("task_id") or old.get("query") or "") != key]
        seen.add(key)
        out.append(item)
    return out


def build_evidence_summary_from_sources(sources: list[dict[str, Any]], *, limit: int = 5) -> str:
    lines: list[str] = []
    for idx, src in enumerate(sources[:limit], start=1):
        lines.append(f"[证据 {idx}]")
        lines.append(f"source: {src.get('source','')}")
        lines.append(f"title_path: {src.get('title_path','')}")
        lines.append(f"chunk_id: {src.get('chunk_id','')}")
        lines.append(f"text: {src.get('preview','')}")
        lines.append("")
    return "\n".join(lines).strip()


def sources_to_evidence_text(sources: list[dict[str, Any]], *, limit: int = 8) -> str:
    return build_evidence_summary_from_sources(sources, limit=limit)
