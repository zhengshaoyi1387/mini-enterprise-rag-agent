from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mini_rag.utils import dump_json_atomic, file_sha256, load_json


@dataclass
class SourceFileState:
    """单个源文件在索引系统里的状态快照。

    新手可以把它理解成“文件身份证”：
    - source：文件在 data/raw 下的相对路径，例如 `manual/a.pdf`。
    - content_hash：文件内容的 SHA256。只要文件内容变了，这个值就会变。
    - modified_time：文件系统里的最后修改时间，主要方便排查。
    - chunk_ids：这个文件切出来并写进 Chroma 的所有 chunk id。

    为什么要保存 chunk_ids？
    因为某个文件更新或删除时，我们要知道应该从 Chroma 里删掉哪些旧向量。
    如果不保存这份映射，就只能粗暴重建整个向量库。
    """

    source: str
    content_hash: str
    modified_time: float
    chunk_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "SourceFileState":
        """把 JSON 里的 dict 还原成 SourceFileState 对象。"""
        return cls(
            source=str(data["source"]),
            content_hash=str(data["content_hash"]),
            modified_time=float(data.get("modified_time", 0.0)),
            chunk_ids=list(data.get("chunk_ids", [])),
        )

    def to_dict(self) -> dict:
        """把 SourceFileState 转成可以写入 JSON 的普通 dict。"""
        return {
            "source": self.source,
            "content_hash": self.content_hash,
            "modified_time": self.modified_time,
            "chunk_ids": self.chunk_ids,
        }


@dataclass
class IndexManifest:
    """整个知识库索引的 manifest。

    manifest 是增量索引的核心文件，默认保存在：
    `storage/index_manifest.json`

    它记录“当前向量库里有哪些源文件、每个源文件对应哪些 chunk”。
    下一次 build-index 时，代码会拿“磁盘上的真实文件”跟 manifest 对比：
    - 新文件：需要加载、切分、向量化。
    - 内容变化的文件：先删除旧 chunk，再写入新 chunk。
    - 没变化的文件：跳过，节省 embedding 调用成本。
    - 已删除的文件：删除 Chroma 里的旧 chunk。
    """

    sources: dict[str, SourceFileState] = field(default_factory=dict)
    version: int = 1

    @classmethod
    def load(cls, path: str | Path) -> "IndexManifest":
        """从磁盘读取 manifest；如果文件不存在，说明这是第一次建索引。"""
        path = Path(path)
        if not path.exists():
            return cls()
        data = load_json(path)
        return cls(
            version=int(data.get("version", 1)),
            sources={
                key: SourceFileState.from_dict(value)
                for key, value in dict(data.get("sources", {})).items()
            },
        )

    def save(self, path: str | Path) -> None:
        """把 manifest 写回磁盘。

        这里用 dump_json_atomic 原子写入：
        先写临时文件，再一次性替换目标文件，避免程序中途崩溃留下半截 JSON。
        """
        dump_json_atomic(
            path,
            {
                "version": self.version,
                "sources": {key: value.to_dict() for key, value in sorted(self.sources.items())},
            },
        )


@dataclass
class IndexChanges:
    """一次 build-index 检测出来的变化结果。

    这个对象不直接操作 Chroma，它只负责告诉后续流程：
    - 哪些文件要重新处理。
    - 哪些文件可以跳过。
    - 哪些旧 chunk id 应该从 Chroma 删除。
    """

    changed_sources: list[str]
    unchanged_sources: list[str]
    deleted_sources: list[str]
    chunk_ids_to_delete: list[str]
    current_states: dict[str, SourceFileState]


def build_source_state(path: str | Path, data_dir: str | Path) -> SourceFileState:
    """根据磁盘上的真实文件生成当前状态快照。"""
    path = Path(path)
    data_dir = Path(data_dir).resolve()
    rel_source = str(path.resolve().relative_to(data_dir))
    return SourceFileState(
        source=rel_source,
        content_hash=file_sha256(path),
        modified_time=path.stat().st_mtime,
        chunk_ids=[],
    )


def detect_index_changes(
    source_files: list[Path],
    data_dir: str | Path,
    previous: IndexManifest,
) -> IndexChanges:
    """比较“磁盘当前文件”和“上次 manifest”，得出增量索引计划。

    这是增量索引最重要的判断逻辑。整体思路：
    1. 先给当前磁盘上的每个文件计算 hash。
    2. 如果 manifest 里没有这个文件，说明是新文件，要处理。
    3. 如果 manifest 里有，但 hash 不一样，说明内容变了，要重建该文件。
    4. 如果 hash 一样，说明文件没变化，可以复用旧 chunk_ids。
    5. 如果 manifest 里有、磁盘上没有，说明文件被删除，要删除旧 chunk。
    """
    current_states = {state.source: state for state in [build_source_state(path, data_dir) for path in source_files]}
    previous_sources = set(previous.sources)
    current_sources = set(current_states)

    changed_sources: list[str] = []
    unchanged_sources: list[str] = []
    chunk_ids_to_delete: list[str] = []

    for source, state in sorted(current_states.items()):
        old_state = previous.sources.get(source)
        if old_state and old_state.content_hash == state.content_hash:
            # 内容 hash 相同，说明这个文件没有变化，不需要重新 embedding。
            # 但它原来对应的 chunk_ids 要保留下来，后面保存新 manifest 时还会用到。
            unchanged_sources.append(source)
            state.chunk_ids = list(old_state.chunk_ids)
        else:
            # 新文件或内容变化的文件都进入 changed_sources。
            # 如果是内容变化，还要先删掉旧 chunk，避免同一文件的新旧内容同时出现在向量库。
            changed_sources.append(source)
            if old_state:
                chunk_ids_to_delete.extend(old_state.chunk_ids)

    deleted_sources = sorted(previous_sources - current_sources)
    for source in deleted_sources:
        # 文件已经从 data/raw 删除了，但 Chroma 不会自动知道。
        # 所以这里把它过去写入的 chunk_ids 收集起来，交给 build_index 统一删除。
        chunk_ids_to_delete.extend(previous.sources[source].chunk_ids)

    return IndexChanges(
        changed_sources=changed_sources,
        unchanged_sources=unchanged_sources,
        deleted_sources=deleted_sources,
        chunk_ids_to_delete=chunk_ids_to_delete,
        current_states=current_states,
    )
