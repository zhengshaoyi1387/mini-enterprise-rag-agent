from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document
from langchain_community.document_loaders import DirectoryLoader, Docx2txtLoader, PyPDFLoader, TextLoader


SUPPORTED_GLOBS = ["**/*.md", "**/*.markdown", "**/*.txt", "**/*.pdf", "**/*.docx"]
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf", ".docx"}


def discover_source_files(data_dir: str | Path) -> list[Path]:
    """扫描当前支持的企业知识库文件。

    这个函数服务于“增量索引”：
    build_index 会先用它找到 data/raw 下所有源文件，再计算每个文件的 hash。
    真正的文档内容读取仍然交给 load_documents_with_langchain。
    """
    data_dir = Path(data_dir)
    files: list[Path] = []
    for path in data_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(path)
    return sorted(files)


def load_documents_with_langchain(data_dir: str | Path, only_sources: set[str] | None = None) -> list[Document]:
    """使用 LangChain 官方常用 Loader 组合加载本地文档。

    重要说明：
    - 这里没有手写自定义 Loader。
    - 使用的是 LangChain 社区包中的 DirectoryLoader + TextLoader。
    - DirectoryLoader 负责扫描目录。
    - TextLoader 负责把每个文本文件读取成 LangChain Document。

    为什么 Markdown 也用 TextLoader？
    - Markdown 本质上是纯文本格式。
    - 加载阶段只需要把原始文本读出来。
    - Markdown 的标题结构切分交给后面的 MarkdownHeaderTextSplitter 处理。
    """
    data_dir = Path(data_dir)
    all_docs: list[Document] = []

    loader_specs = [
        ("**/*.md", TextLoader, {"encoding": "utf-8", "autodetect_encoding": True}),
        ("**/*.markdown", TextLoader, {"encoding": "utf-8", "autodetect_encoding": True}),
        ("**/*.txt", TextLoader, {"encoding": "utf-8", "autodetect_encoding": True}),
        ("**/*.pdf", PyPDFLoader, {}),
        ("**/*.docx", Docx2txtLoader, {}),
    ]

    for glob_pattern, loader_cls, loader_kwargs in loader_specs:
        # DirectoryLoader 是现代 LangChain 项目里常用的本地目录加载器。
        # 不同文件格式只替换 loader_cls：
        # - TextLoader：读取 md / txt 这种纯文本。
        # - PyPDFLoader：按页读取 PDF，metadata 里通常会带 page。
        # - Docx2txtLoader：读取 Word 文档正文。
        loader = DirectoryLoader(
            path=str(data_dir),
            glob=glob_pattern,
            loader_cls=loader_cls,
            loader_kwargs=loader_kwargs,
            # 多线程可以加快大量小文件的 I/O 加载。
            use_multithreading=True,
            show_progress=True,
            # 遇到单个坏文件时不让整个加载流程中断。
            silent_errors=True,
        )
        all_docs.extend(loader.load())

    normalized = normalize_loaded_documents(all_docs, data_dir)
    if only_sources is None:
        return normalized
    # 增量索引时只处理变化文件；没变化的文件直接复用旧 manifest 和 Chroma 里的向量。
    return [doc for doc in normalized if doc.metadata.get("source") in only_sources]


def normalize_loaded_documents(docs: list[Document], data_dir: Path) -> list[Document]:
    """统一整理 LangChain Loader 返回的 metadata。

    这一步不是自定义 Loader，只是把不同 Loader 可能返回的 source 路径整理成稳定格式。
    企业知识库项目里 metadata 非常重要，因为最终回答要引用来源。
    """
    normalized: list[Document] = []
    data_dir = data_dir.resolve()

    for doc in docs:
        raw_source = doc.metadata.get("source", "")
        source_path = Path(raw_source).resolve() if raw_source else None

        if source_path:
            try:
                # source 用相对路径，避免把你电脑上的绝对路径暴露给最终用户。
                rel_source = str(source_path.relative_to(data_dir))
            except ValueError:
                rel_source = source_path.name
        else:
            rel_source = "unknown"

        file_name = Path(rel_source).name
        file_type = Path(rel_source).suffix.lower()

        content = doc.page_content or ""
        if not content.strip():
            # 空文档不进入后续流程，避免污染向量库。
            continue

        metadata = dict(doc.metadata or {})
        metadata.update(
            {
                "source": rel_source,
                "file_name": file_name,
                "file_type": file_type,
                "loader": detect_loader_name(file_type),
            }
        )

        if "page" in metadata:
            # PyPDFLoader 的 page 通常从 0 开始；给用户看的页码从 1 开始更自然。
            metadata["page_number"] = int(metadata["page"]) + 1

        normalized.append(Document(page_content=content, metadata=metadata))

    return normalized


def detect_loader_name(file_type: str) -> str:
    if file_type == ".pdf":
        return "DirectoryLoader+PyPDFLoader"
    if file_type == ".docx":
        return "DirectoryLoader+Docx2txtLoader"
    return "DirectoryLoader+TextLoader"
