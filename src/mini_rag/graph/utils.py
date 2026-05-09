from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

METADATA_FIELD_PATTERN = re.compile(
    r"(?im)^\s*[-*]?\s*(source|title_path|titlepath|chunk_id|chunkid|vector_score|bm25_score|rrf_score|rerank_score|rank|preview)\s*[:：].*$"
)
REFERENCE_BLOCK_PATTERN = re.compile(r"(?is)(引用来源|来源|Sources?|References?)\s*[:：].*$")


def now_ms() -> float:
    return time.perf_counter() * 1000


@dataclass
class NodeTimer:
    state: dict[str, Any]
    node: str

    def __enter__(self):
        self.start = now_ms()
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed = round(now_ms() - self.start, 2)
        # Keep trace useful but compact. The full state can be inspected via
        # top-level trace fields; per-node listing every key bloats logs without
        # improving debugging quality.
        self.state.setdefault("node_trace", []).append(
            {
                "node": self.node,
                "latency_ms": elapsed,
                "route": self.state.get("route", ""),
                "error": str(exc) if exc else self.state.get("error"),
                "state": {
                    "intent": self.state.get("intent", ""),
                    "message_type": self.state.get("message_type", ""),
                    "selected_tool": self.state.get("selected_tool"),
                    "selected_action": self.state.get("selected_action"),
                },
            }
        )
        return False


def strip_citations_and_metadata(text: str) -> str:
    text = text or ""
    text = REFERENCE_BLOCK_PATTERN.sub("", text)
    lines = []
    for line in text.splitlines():
        if METADATA_FIELD_PATTERN.match(line):
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def safe_json_loads(text: str, default: Any) -> Any:
    if not text or not isinstance(text, str):
        return default
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return default
        return default


def coerce_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [value]
    return []


def dedupe_keep_order(items: list[Any], key: Callable[[Any], str] | None = None) -> list[Any]:
    seen: set[str] = set()
    output: list[Any] = []
    for item in items:
        marker = key(item) if key else str(item)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output


def truncate(text: str, limit: int = 700) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def get_message_content(message: Any) -> str:
    if isinstance(message, str):
        return message
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part) for part in content)
    return str(message)


def document_key(doc: Any) -> str:
    md = getattr(doc, "metadata", None) or {}
    return str(md.get("chunk_id") or md.get("source") or getattr(doc, "page_content", "")[:80])


def document_to_source(doc: Any) -> dict[str, Any]:
    md = getattr(doc, "metadata", None) or {}
    content = getattr(doc, "page_content", "") or ""
    return {
        "rank": md.get("rank"),
        "kb_id": md.get("kb_id"),
        "kb_name": md.get("kb_name"),
        "source": md.get("source"),
        "title_path": md.get("title_path"),
        "chunk_id": md.get("chunk_id"),
        "vector_score": md.get("vector_score"),
        "bm25_score": md.get("bm25_score"),
        "rrf_score": md.get("rrf_score"),
        "rerank_score": md.get("rerank_score"),
        "preview": content[:240],
    }


def format_evidence_text(docs: list[Any], limit_each: int = 900) -> str:
    blocks: list[str] = []
    for idx, doc in enumerate(docs, start=1):
        md = getattr(doc, "metadata", None) or {}
        content = truncate(getattr(doc, "page_content", "") or "", limit_each)
        blocks.append(
            "\n".join(
                [
                    f"[证据 {idx}]",
                    f"kb_id: {md.get('kb_id', 'unknown')}",
                    f"source: {md.get('source', 'unknown')}",
                    f"title_path: {md.get('title_path', 'unknown')}",
                    f"chunk_id: {md.get('chunk_id', 'unknown')}",
                    f"text: {content}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _contains_entity(doc: Any, entity: str) -> bool:
    entity = str(entity or "").strip()
    if not entity:
        return False
    md = getattr(doc, "metadata", None) or {}
    text = " ".join(
        [
            str(md.get("title_path", "")),
            str(md.get("section", "")),
            str(md.get("source", "")),
            str(getattr(doc, "page_content", "") or ""),
        ]
    )
    return entity in text


def compact_evidence_text(
    docs: list[Any],
    entities: list[str] | None = None,
    limit_each: int = 260,
    max_total_chars: int = 2200,
) -> str:
    docs = dedupe_keep_order(docs, key=document_key)
    selected: list[Any] = []
    for entity in entities or []:
        matched = [doc for doc in docs if _contains_entity(doc, entity)]
        selected.extend(matched[:2])
    selected.extend(docs[:5])
    selected = dedupe_keep_order(selected, key=document_key)
    blocks: list[str] = []
    total = 0
    for idx, doc in enumerate(selected, start=1):
        md = getattr(doc, "metadata", None) or {}
        content = truncate(str(getattr(doc, "page_content", "") or ""), limit_each)
        block = "\n".join(
            [
                f"[证据 {idx}]",
                f"source: {md.get('source', 'unknown')}",
                f"title_path: {md.get('title_path', 'unknown')}",
                f"chunk_id: {md.get('chunk_id', 'unknown')}",
                f"text: {content}",
            ]
        )
        if total + len(block) > max_total_chars:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)
