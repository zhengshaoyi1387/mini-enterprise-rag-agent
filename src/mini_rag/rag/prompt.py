"""兼容旧导入路径的 prompt re-export。

新的提示词统一放在 mini_rag.prompts 包中。
保留这个文件是为了不破坏已有代码里的 `from mini_rag.rag.prompt import ...`。
"""

from mini_rag.prompts import AGENT_SYSTEM_PROMPT, RAG_SYSTEM_PROMPT

__all__ = ["AGENT_SYSTEM_PROMPT", "RAG_SYSTEM_PROMPT"]
