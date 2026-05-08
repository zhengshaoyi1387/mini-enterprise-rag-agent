from __future__ import annotations

from langchain_core.documents import Document


def format_documents_as_evidence(docs: list[Document]) -> str:
    """把检索到的文档格式化成给 LLM 看的证据文本。

    这里把 metadata 放在正文前面，是为了让模型知道每段证据来自哪里。
    """
    blocks: list[str] = []

    for index, doc in enumerate(docs, start=1):
        md = doc.metadata or {}
        blocks.append(
            f"""
【证据 {index}】
kb_id: {md.get('kb_id')}
source: {md.get('source')}
title_path: {md.get('title_path')}
chunk_id: {md.get('chunk_id')}
content:
{doc.page_content}
""".strip()
        )

    return "\n\n".join(blocks)


def format_sources(docs: list[Document]) -> list[dict]:
    """提取引用来源，供 API 响应或 trace 使用。"""
    sources = []
    for doc in docs:
        md = doc.metadata or {}
        sources.append(
            {
                "rank": md.get("rank"),
                "kb_id": md.get("kb_id"),
                "kb_name": md.get("kb_name"),
                "source": md.get("source"),
                "title_path": md.get("title_path"),
                "chunk_id": md.get("chunk_id"),
                "vector_score": md.get("vector_score"),
                "preview": doc.page_content[:200],
            }
        )
    return sources
