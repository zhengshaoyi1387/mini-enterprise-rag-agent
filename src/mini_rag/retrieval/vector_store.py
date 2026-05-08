from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from mini_rag.config import Settings


def create_vector_store(settings: Settings, embeddings: Embeddings) -> Chroma:
    """创建 Chroma 向量库对象。

    Chroma 支持本地持久化，适合学习项目和中小型 demo。
    persist_directory 指向 storage/chroma，重启程序后索引仍然存在。
    """
    return Chroma(
        collection_name=settings.collection_name,
        embedding_function=embeddings,
        persist_directory=str(settings.chroma_dir),
    )


def delete_documents_by_ids(vector_store: Chroma, ids: list[str]) -> None:
    """按 chunk id 删除旧向量；Chroma 对空列表不需要调用。"""
    if ids:
        vector_store.delete(ids=ids)
