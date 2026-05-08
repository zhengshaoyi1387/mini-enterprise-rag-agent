from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any


def stable_hash(text: str, length: int = 12) -> str:
    """生成稳定短哈希。

    为什么需要它？
    - 向量库里的每个 chunk 都最好有稳定 ID。
    - 只要文件路径和内容不变，ID 就不变，便于去重、更新和引用。
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在，并返回 Path 对象。"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def dump_json(path: str | Path, data: Any) -> None:
    """把 Python 对象保存为格式化 JSON。

    ensure_ascii=False 可以保留中文，不会把中文转成 \\uXXXX。
    """
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_json_atomic(path: str | Path, data: Any) -> None:
    """原子写 JSON，避免索引 manifest 写到一半时被中断留下坏文件。"""
    path = Path(path)
    ensure_dir(path.parent)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def load_json(path: str | Path) -> Any:
    """读取 JSON 文件。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_sha256(path: str | Path) -> str:
    """计算文件内容哈希，用于判断文档是否发生变化。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimate_tokens_for_chinese(text: str) -> int:
    """粗略估算 token 数。

    真实 token 数要依赖具体 tokenizer。为了避免引入复杂依赖，
    这里用一个经验估算：中文场景大约 1.5~2 个汉字对应 1 个 token。
    这个值只用于 metadata 展示，不影响模型调用。
    """
    return max(1, len(text) // 2)
