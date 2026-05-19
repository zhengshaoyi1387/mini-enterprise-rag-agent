from __future__ import annotations

from typing import Any

RAG_SYSTEM_PROMPT = """
你是严谨的企业知识库问答助手。

回答规则：
1. 只能基于用户提供的证据回答。
2. 如果证据不足，必须明确说明证据不足，不能编造制度内容。
3. 回答要简洁、结构清晰，优先使用中文。
4. 回答末尾必须列出引用来源，至少包含 source、title_path、chunk_id。
""".strip()

AGENT_SYSTEM_PROMPT = RAG_SYSTEM_PROMPT


def format_final_user_prompt(
    question: str,
    standalone_query: str,
    summary: str,
    evidence_assessment: dict[str, Any] | None,
    evidence_text: str,
) -> str:
    """Build the plain RAG answer prompt used by ``RAGQuestionAnswerer``.

    The current Agent prompt stack lives in ``mini_rag.graph.prompts``. This
    module keeps only the small standalone RAG helper that is still imported by
    ``mini_rag.rag.chain`` and the unified eval suite.
    """

    return "\n\n".join(
        [
            f"用户原始问题：{question}",
            f"独立检索问题：{standalone_query}",
            f"会话摘要：{summary or '无'}",
            f"【证据评估】\n{evidence_assessment or '无'}",
            f"【证据】\n{evidence_text or '无'}",
        ]
    )


__all__ = ["AGENT_SYSTEM_PROMPT", "RAG_SYSTEM_PROMPT", "format_final_user_prompt"]
