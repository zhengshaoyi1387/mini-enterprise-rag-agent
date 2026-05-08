from __future__ import annotations

"""Knowledge-base catalog and lightweight kb_id inference.

The project keeps permission rules at the knowledge-base level, not at the
chunk level. Each chunk only stores ``kb_id`` so the retriever can filter before
retrieval and avoid leaking unauthorized documents into the LLM context.
"""

from pathlib import Path
from typing import Any

KNOWLEDGE_BASES: dict[str, dict[str, str]] = {
    "public": {
        "name": "公共知识库",
        "description": "全员可访问的公司通用制度、FAQ、组织沟通和知识库说明。",
    },
    "hr": {
        "name": "人事知识库",
        "description": "人事、考勤、假勤、培训、绩效、入转调离相关制度。",
    },
    "finance": {
        "name": "财务知识库",
        "description": "报销、差旅、采购、预算、发票、财务审批相关制度。",
    },
    "it": {
        "name": "IT 知识库",
        "description": "账号权限、API Key、办公网络、IT 资产、故障工单相关规范。",
    },
    "product": {
        "name": "产品知识库",
        "description": "产品手册、客户方案、智能客服、工单系统、Agent/RAG 使用规范。",
    },
}


def list_knowledge_bases() -> list[dict[str, str]]:
    """Return a stable list for admin UI/API."""

    return [
        {"kb_id": kb_id, **meta}
        for kb_id, meta in KNOWLEDGE_BASES.items()
    ]


def normalize_kb_ids(kb_ids: list[str] | None) -> list[str]:
    """Normalize external kb_ids and drop unknown values."""

    if not kb_ids:
        return []
    valid = set(KNOWLEDGE_BASES)
    normalized: list[str] = []
    for item in kb_ids:
        kb_id = str(item or "").strip().lower()
        if kb_id in valid and kb_id not in normalized:
            normalized.append(kb_id)
    return normalized


def infer_kb_id_from_source(source: str | Path) -> str:
    """Infer kb_id from path/name.

    Preferred layout:
        data/kbs/<kb_id>/xxx.md

    Backward-compatible layout:
        data/raw/*.md
    In that case we infer from Chinese/English keywords in the filename.
    """

    path = Path(str(source))
    parts = [p.lower() for p in path.parts]
    if "kbs" in parts:
        idx = parts.index("kbs")
        if idx + 1 < len(parts):
            candidate = parts[idx + 1]
            if candidate in KNOWLEDGE_BASES:
                return candidate

    text = str(source).lower()
    rules: list[tuple[str, list[str]]] = [
        ("finance", ["财务", "报销", "采购", "预算", "发票", "finance", "reimbursement"]),
        ("hr", ["人事", "考勤", "假勤", "培训", "绩效", "员工", "入职", "离职", "hr"]),
        ("it", ["it", "账号", "权限", "api key", "网络", "设备", "vpn", "故障", "trace", "日志", "安全"]),
        ("product", ["产品", "智能客服", "工单", "agent", "rag", "客户", "销售", "poc", "解决方案"]),
    ]
    for kb_id, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return kb_id
    return "public"


def kb_metadata(kb_id: str) -> dict[str, Any]:
    meta = KNOWLEDGE_BASES.get(kb_id) or KNOWLEDGE_BASES["public"]
    return {"kb_id": kb_id, "kb_name": meta["name"]}
