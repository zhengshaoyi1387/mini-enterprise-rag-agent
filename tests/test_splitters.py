from langchain_core.documents import Document

from mini_rag.config import Settings
from mini_rag.ingestion.splitters import split_documents


def test_markdown_splitter_generates_title_path():
    """测试 Markdown 标题路径是否能写入 metadata。"""
    doc = Document(
        page_content="# 手册\n\n## 产品概述\n\n这是产品介绍。\n\n## 使用说明\n\n这是使用说明。",
        metadata={
            "source": "kbs/finance/manual.md",
            "file_name": "manual.md",
            "file_type": ".md",
        },
    )
    chunks = split_documents([doc], Settings(DASHSCOPE_API_KEY="test-key"))
    assert chunks
    assert "title_path" in chunks[0].metadata
    assert chunks[0].metadata["chunk_id"]
    assert chunks[0].metadata["kb_id"] == "finance"
    assert chunks[0].metadata["kb_name"] == "财务知识库"
