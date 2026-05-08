from __future__ import annotations

import shutil

from mini_rag.config import Settings
from mini_rag.ingestion.loaders import discover_source_files, load_documents_with_langchain
from mini_rag.ingestion.manifest import IndexManifest, detect_index_changes
from mini_rag.ingestion.splitters import split_documents
from mini_rag.models.qwen import build_qwen_embeddings
from mini_rag.retrieval.vector_store import create_vector_store, delete_documents_by_ids
from mini_rag.utils import ensure_dir


def build_index(settings: Settings, reset: bool = False) -> dict:
    """构建 Chroma 向量索引。

    参数：
    - reset=True：先删除旧的 Chroma 存储目录，再重新构建索引。
    - reset=False：在现有 collection 上继续追加。学习阶段建议 reset=True，避免重复数据。
    """
    # reset=True 用于“干净重建”。学习/演示时如果担心索引脏了，可以直接 --reset。
    # 注意：正常企业项目更常用增量索引，不会每次都删库重建，因为 embedding 调用有成本。
    if reset and settings.chroma_dir.exists():
        shutil.rmtree(settings.chroma_dir)

    if reset and settings.index_manifest_path.exists():
        settings.index_manifest_path.unlink()

    ensure_dir(settings.chroma_dir)
    ensure_dir(settings.index_manifest_path.parent)

    # previous_manifest 是“上一次构建索引时的记录”。
    # 如果是 reset，就把它当成空 manifest，表示所有文件都需要重新处理。
    previous_manifest = IndexManifest.load(settings.index_manifest_path) if not reset else IndexManifest()

    # 先扫描 data/raw 里所有支持格式的文件，再跟 manifest 对比。
    # 这里还没有真正读取文件内容给 LangChain，只是做“文件级变化检测”。
    source_files = discover_source_files(settings.data_dir)
    changes = detect_index_changes(source_files, settings.data_dir, previous_manifest)

    # 1. 增量加载发生变化的原始文档。
    # only_sources 的作用是：没变化的文件不再加载、不再切分、不再调用 embedding。
    raw_docs = load_documents_with_langchain(settings.data_dir, only_sources=set(changes.changed_sources))

    # 2. 切成适合检索的 chunks。
    chunks = split_documents(raw_docs, settings)

    # 3. 构造 Qwen Embedding。
    embeddings = build_qwen_embeddings(settings)

    # 4. 创建 Chroma 向量库。
    vector_store = create_vector_store(settings, embeddings)

    # 5. 删除已变化/已删除文件对应的旧 chunk，再写入新 chunk。
    # 顺序必须是“先删旧、再写新”，否则同一个文件的旧内容和新内容会同时被检索到。
    delete_documents_by_ids(vector_store, changes.chunk_ids_to_delete)

    #    ids 使用 chunk_id，便于后续追踪。
    ids = [doc.metadata["chunk_id"] for doc in chunks]
    if chunks:
        # DashScope/Qwen embedding endpoint limits a single embedding batch.
        # Chroma.add_documents calls embed_documents internally, so we must
        # batch here instead of submitting all chunks at once.
        embedding_batch_size = 10
        total_batches = (len(chunks) + embedding_batch_size - 1) // embedding_batch_size
        for batch_index, start in enumerate(range(0, len(chunks), embedding_batch_size), start=1):
            end = start + embedding_batch_size
            batch_chunks = chunks[start:end]
            batch_ids = ids[start:end]
            print(f"[build_index] adding batch {batch_index}/{total_batches}, size={len(batch_chunks)}")
            vector_store.add_documents(documents=batch_chunks, ids=batch_ids)

    # 6. 生成新的 manifest。
    # 没变化的文件沿用旧 chunk_ids；变化的文件使用这次新生成的 chunk_ids。
    # 最终 manifest 应该准确描述“当前 Chroma 里应该存在的全部源文件和 chunk”。
    next_manifest = IndexManifest()
    next_manifest.sources = changes.current_states
    for source in changes.unchanged_sources:
        old_state = previous_manifest.sources[source]
        next_manifest.sources[source].chunk_ids = list(old_state.chunk_ids)
    for doc in chunks:
        source = doc.metadata.get("source")
        if source in next_manifest.sources:
            next_manifest.sources[source].chunk_ids.append(doc.metadata["chunk_id"])
    next_manifest.save(settings.index_manifest_path)

    return {
        "raw_document_count": len(raw_docs),
        "chunk_count": len(chunks),
        "changed_source_count": len(changes.changed_sources),
        "unchanged_source_count": len(changes.unchanged_sources),
        "deleted_source_count": len(changes.deleted_sources),
        "deleted_chunk_count": len(changes.chunk_ids_to_delete),
        "collection_name": settings.collection_name,
        "chroma_dir": str(settings.chroma_dir),
        "manifest_path": str(settings.index_manifest_path),
    }
