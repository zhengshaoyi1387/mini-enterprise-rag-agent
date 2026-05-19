from __future__ import annotations

"""Small filesystem-backed admin helpers for knowledge-base documents."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mini_rag.config import Settings
from mini_rag.ingestion.kb_config import KNOWLEDGE_BASES
from mini_rag.ingestion.loaders import SUPPORTED_SUFFIXES
from mini_rag.utils import ensure_dir

TEXT_IMPORT_SUFFIXES = {".md", ".markdown", ".txt"}


def list_kbs_with_documents(settings: Settings) -> list[dict[str, Any]]:
    """Return configured KB metadata plus source files currently on disk."""

    items: list[dict[str, Any]] = []
    for kb_id, meta in KNOWLEDGE_BASES.items():
        documents = list_kb_documents(settings, kb_id)
        items.append(
            {
                "kb_id": kb_id,
                **meta,
                "file_count": len(documents),
                "total_size_bytes": sum(int(doc.get("size_bytes") or 0) for doc in documents),
                "documents": documents,
            }
        )
    return items


def list_kb_documents(settings: Settings, kb_id: str) -> list[dict[str, Any]]:
    kb_dir = _kb_dir(settings, kb_id, create=False)
    if not kb_dir.exists():
        return []
    documents: list[dict[str, Any]] = []
    for path in sorted(p for p in kb_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES):
        documents.append(_document_info(settings, kb_id, path, include_preview=True))
    return documents


def import_kb_document(settings: Settings, kb_id: str, filename: str, content: str, overwrite: bool = False) -> dict[str, Any]:
    """Write a text source document under ``data/kbs/<kb_id>/``."""

    path = _safe_document_path(settings, kb_id, filename, create_parent=True)
    suffix = path.suffix.lower()
    if suffix not in TEXT_IMPORT_SUFFIXES:
        raise ValueError(f"Only Markdown/text files can be imported from the web UI: {sorted(TEXT_IMPORT_SUFFIXES)}")
    if path.exists() and not overwrite:
        raise FileExistsError(f"Knowledge-base document already exists: {path.name}")
    text = content.strip()
    if not text:
        raise ValueError("Document content cannot be empty")
    path.write_text(text + "\n", encoding="utf-8")
    info = _document_info(settings, kb_id, path, include_preview=True)
    info["requires_reindex"] = True
    return info


def delete_kb_document(settings: Settings, kb_id: str, document_path: str) -> dict[str, Any]:
    path = _safe_document_path(settings, kb_id, document_path, create_parent=False)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Knowledge-base document not found: {document_path}")
    info = _document_info(settings, kb_id, path, include_preview=False)
    path.unlink()
    info["requires_reindex"] = True
    return info


def _kb_dir(settings: Settings, kb_id: str, create: bool) -> Path:
    normalized = str(kb_id or "").strip().lower()
    if normalized not in KNOWLEDGE_BASES:
        raise ValueError(f"Unknown knowledge base: {kb_id}")
    root = Path(settings.data_dir)
    target = root / normalized
    if create:
        ensure_dir(target)
    return target


def _safe_document_path(settings: Settings, kb_id: str, document_path: str, create_parent: bool) -> Path:
    kb_dir = _kb_dir(settings, kb_id, create=create_parent).resolve()
    raw = str(document_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("Document path cannot be empty")
    parts = [part for part in raw.split("/") if part and part != "."]
    normalized_kb = str(kb_id or "").strip().lower()
    if parts and parts[0].lower() == normalized_kb:
        parts = parts[1:]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("Invalid document path")
    target = (kb_dir / Path(*parts)).resolve()
    if kb_dir not in target.parents and target != kb_dir:
        raise ValueError("Document path escapes the knowledge-base directory")
    if target.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported document type: {target.suffix or '(none)'}")
    if create_parent:
        ensure_dir(target.parent)
    return target


def _document_info(settings: Settings, kb_id: str, path: Path, include_preview: bool) -> dict[str, Any]:
    data_dir = Path(settings.data_dir).resolve()
    rel_path = path.resolve().relative_to(data_dir)
    stat = path.stat()
    info: dict[str, Any] = {
        "kb_id": kb_id,
        "filename": path.name,
        "path": rel_path.as_posix(),
        "file_type": path.suffix.lower(),
        "size_bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "requires_reindex": False,
    }
    if include_preview and path.suffix.lower() in TEXT_IMPORT_SUFFIXES:
        try:
            preview = path.read_text(encoding="utf-8", errors="ignore").strip().replace("\n", " ")
        except OSError:
            preview = ""
        info["preview"] = preview[:180]
    return info
