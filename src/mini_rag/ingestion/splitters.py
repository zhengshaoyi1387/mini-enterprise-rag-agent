from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from mini_rag.config import Settings
from mini_rag.utils import estimate_tokens_for_chinese, stable_hash
from mini_rag.ingestion.kb_config import infer_kb_id_from_source, kb_metadata


# MarkdownHeaderTextSplitter 会把这些标题层级写入 metadata。
# 例如：# 标题 -> h1，## 标题 -> h2。
MARKDOWN_HEADERS = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
    ("#####", "h5"),
    ("######", "h6"),
]


def split_documents(docs: list[Document], settings: Settings) -> list[Document]:
    """把原始 Document 切成适合向量检索的 chunks。

    整体策略：
    1. Markdown 文件先用 MarkdownHeaderTextSplitter 按标题切成 section。
    2. TXT 文件没有标题结构，直接作为普通文本处理。
    3. 所有 section 再统一用 RecursiveCharacterTextSplitter 做二次切分。
    4. 最后补充 chunk_id、title_path、content_hash 等 metadata。

    新手理解：
    - Loader 负责“读文件”。
    - Splitter 负责“切知识块”。
    - Embedding 负责“把知识块变成向量”。
    """
    section_docs: list[Document] = []

    for doc in docs:
        file_type = doc.metadata.get("file_type", "").lower()
        if file_type in {".md", ".markdown"}:
            section_docs.extend(split_markdown_document(doc))
        else:
            section_docs.append(make_plain_text_section(doc))

    chunks = split_sections_into_chunks(section_docs, settings)
    return add_chunk_metadata(chunks)


def split_markdown_document(doc: Document) -> list[Document]:
    """使用 LangChain 官方 MarkdownHeaderTextSplitter 切分 Markdown。

    这里没有自己写正则解析 Markdown，而是使用 LangChain 提供的 splitter。
    它会根据 #、##、### 等标题，把正文拆成多个 Document，并把标题层级放到 metadata。
    """
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=MARKDOWN_HEADERS,
        # strip_headers=False 表示保留标题文本在 page_content 里。
        # 这样 embedding 时也能看到标题，有利于检索。
        strip_headers=False,
    )

    split_docs = splitter.split_text(doc.page_content)
    results: list[Document] = []

    for index, section_doc in enumerate(split_docs):
        content = section_doc.page_content or ""
        if not content.strip():
            continue

        # 合并原始文件 metadata 和 Markdown 标题 metadata。
        metadata = dict(doc.metadata)
        metadata.update(section_doc.metadata or {})

        title_path = build_title_path(metadata, fallback=metadata.get("file_name", "unknown"))
        section = get_deepest_heading(metadata) or metadata.get("file_name", "unknown")
        source = metadata.get("source", "unknown")
        kb_id = str(metadata.get("kb_id") or infer_kb_id_from_source(source))

        metadata.update(
            {
                "title_path": title_path,
                **kb_metadata(kb_id),
                "section": section,
                "section_index": index,
                "content_type": "markdown_heading_section",
                "locator_type": "markdown_header_path",
            }
        )

        results.append(Document(page_content=content, metadata=metadata))

    # 如果一个 Markdown 文件没有任何标题，MarkdownHeaderTextSplitter 可能返回空。
    # 这种情况下退化为普通文本 section。
    if not results:
        return [make_plain_text_section(doc)]

    return results


def make_plain_text_section(doc: Document) -> Document:
    """把普通文本文件包装成一个 section。

    TXT 没有 Markdown 标题层级，所以 title_path 直接使用文件名。
    """
    metadata = dict(doc.metadata)
    file_name = metadata.get("file_name", metadata.get("source", "unknown"))
    locator = file_name
    if metadata.get("page_number"):
        locator = f"{file_name} > page {metadata['page_number']}"

    metadata.update(
        {
            "title_path": locator,
            "section": locator,
            "section_index": 0,
            "content_type": "plain_text",
            "locator_type": "page" if metadata.get("page_number") else "file",
        }
    )
    return Document(page_content=doc.page_content, metadata=metadata)


def split_sections_into_chunks(section_docs: list[Document], settings: Settings) -> list[Document]:
    """对 section 做二次切分。

    为什么要二次切分？
    - 一个 Markdown 小节可能仍然很长。
    - 向量检索更适合粒度适中的 chunk。
    - chunk 太长会稀释语义，太短会丢上下文。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        # 这些分隔符对中文文档比较友好。
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
    )
    return splitter.split_documents(section_docs)


def add_chunk_metadata(chunks: list[Document]) -> list[Document]:
    """给每个 chunk 补充稳定 metadata。

    chunk_id 是后续引用、去重和 trace 分析的核心字段。
    """
    results: list[Document] = []

    for index, chunk in enumerate(chunks):
        content = chunk.page_content or ""
        if not content.strip():
            continue

        metadata = dict(chunk.metadata or {})
        source = metadata.get("source", "unknown")
        title_path = metadata.get("title_path", metadata.get("file_name", "unknown"))
        # Permissions are configured at knowledge-base level. Each chunk only
        # stores kb_id/kb_name as ownership metadata so retrieval can be
        # filtered before unauthorized content enters the LLM context.
        kb_id = str(metadata.get("kb_id") or infer_kb_id_from_source(source))

        doc_id = stable_hash(source)
        content_hash = stable_hash(content, length=8)
        chunk_id = f"{doc_id}:chunk:{index:04d}:{content_hash}"

        metadata.update(
            {
                "doc_id": doc_id,
                "chunk_index": index,
                "chunk_id": chunk_id,
                "content_hash": content_hash,
                "token_estimate": estimate_tokens_for_chinese(content),
                "title_path": title_path,
                **kb_metadata(kb_id),
            }
        )

        results.append(Document(page_content=content, metadata=metadata))

    return results


def build_title_path(metadata: dict, fallback: str) -> str:
    """根据 MarkdownHeaderTextSplitter 产生的 h1/h2/h3... 组装 title_path。"""
    parts = []
    for key in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        value = metadata.get(key)
        if value:
            parts.append(str(value))
    return " > ".join(parts) if parts else fallback


def get_deepest_heading(metadata: dict) -> str | None:
    """取最深层标题作为当前 section 名称。"""
    for key in ["h6", "h5", "h4", "h3", "h2", "h1"]:
        value = metadata.get(key)
        if value:
            return str(value)
    return None
