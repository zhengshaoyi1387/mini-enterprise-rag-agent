from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from mini_rag.rag.citation import format_sources
from mini_rag.retrieval.retriever import KnowledgeBaseRetriever


class SearchKnowledgeBaseInput(BaseModel):
    """search_knowledge_base 工具的输入参数。"""

    query: str = Field(description="需要在企业知识库中检索的问题或关键词")


class QueryRewriteInput(BaseModel):
    """rewrite_query 工具输入。

    Agent 在遇到追问时会传入当前问题，例如“它有哪些模块？”。
    工具会把最近几轮历史拼进去，帮助后续检索拿到更完整的问题。
    """

    question: str = Field(description="用户当前问题")


class CompareSourcesInput(BaseModel):
    """compare_sources 工具输入，用于“比较 A 和 B”这类问题。"""

    query: str = Field(description="用于对比来源的问题")


class SummarizeSourcesInput(BaseModel):
    """summarize_sources 工具输入，用于“总结某个制度/手册”这类问题。"""

    query: str = Field(description="需要总结证据的主题")


def create_search_knowledge_base_tool(
    retriever: KnowledgeBaseRetriever,
    runtime_trace: dict[str, Any],
    retrieval_mode: str | None = None,
    enable_rerank: bool | None = None,
) -> StructuredTool:
    """创建 search_knowledge_base 工具。

    为什么用工厂函数？
    - 工具函数需要访问 retriever。
    - 每次用户提问都需要独立 trace。
    - 用闭包可以把 retriever 和 trace 注入到工具里。
    """

    def search_knowledge_base(query: str) -> str:
        """检索企业知识库，返回与问题相关的证据。"""
        docs, retrieval_trace = retriever.search(
            query,
            retrieval_mode=retrieval_mode,
            enable_rerank=enable_rerank,
        )

        # 把工具调用过程写进 runtime_trace，方便后续分析 Agent 延迟。
        runtime_trace.setdefault("tool_events", []).append(
            {
                "tool_name": "search_knowledge_base",
                "input": {"query": query},
                "retrieval_trace": retrieval_trace,
            }
        )

        payload = {
            "ok": True,
            "tool_name": "search_knowledge_base",
            "query": query,
            "answer_instruction": "请只基于 evidences 中的 text 回答；如果证据不足，说明当前证据不足以回答；回答时引用 source、title_path、chunk_id。",
            "evidence_count": len(docs),
            "evidences": [
                {
                    "rank": doc.metadata.get("rank"),
                    "text": doc.page_content,
                    "source": doc.metadata.get("source"),
                    "title_path": doc.metadata.get("title_path"),
                    "chunk_id": doc.metadata.get("chunk_id"),
                    "vector_score": doc.metadata.get("vector_score"),
                }
                for doc in docs
            ],
            "sources": format_sources(docs),
        }

        # 工具返回字符串最稳妥，Agent 可以直接读取其中的 JSON 证据。
        return json.dumps(payload, ensure_ascii=False, indent=2)

    return StructuredTool.from_function(
        func=search_knowledge_base,
        name="search_knowledge_base",
        description=(
            "当用户问题涉及企业知识库、制度、产品手册、项目文档、内部说明或 RAG 项目资料时，"
            "调用该工具检索相关证据。工具会返回 evidences，每条证据包含 text、source、title_path、chunk_id。"
        ),
        args_schema=SearchKnowledgeBaseInput,
    )


def create_rewrite_query_tool(runtime_trace: dict[str, Any], session_history: list) -> StructuredTool:
    """创建轻量追问改写工具，把多轮上下文显式暴露给 Agent。

    这里没有再调用一次 LLM 来改写问题，而是把历史问答和当前追问拼成一段文本。
    这样实现简单、稳定、便宜，适合作为教学项目里的“查询改写”版本。
    """

    def rewrite_query(question: str) -> str:
        history_lines = []
        for turn in session_history[-3:]:
            # 只取最近 3 轮，避免工具返回内容过长。
            history_lines.append(f"用户：{turn.question}\n助手：{turn.answer}")
        standalone = question if not history_lines else "\n".join(history_lines + [f"当前追问：{question}"])
        runtime_trace.setdefault("tool_events", []).append(
            {
                "tool_name": "rewrite_query",
                "input": {"question": question},
                "history_turn_count": len(session_history),
                "output_preview": standalone[:300],
            }
        )
        return standalone

    return StructuredTool.from_function(
        func=rewrite_query,
        name="rewrite_query",
        description="当用户问题是追问、省略了主语或需要结合会话历史时，先调用该工具生成独立检索问题。",
        args_schema=QueryRewriteInput,
    )


def create_summarize_sources_tool(
    retriever: KnowledgeBaseRetriever,
    runtime_trace: dict[str, Any],
    retrieval_mode: str | None = None,
    enable_rerank: bool | None = None,
) -> StructuredTool:
    """创建资料总结工具。

    它底层仍然先检索知识库，只是返回给 Agent 的 JSON 更偏“摘要材料”：
    包括来源列表和每段证据的前 500 字。
    """

    def summarize_sources(query: str) -> str:
        docs, retrieval_trace = retriever.search(query, retrieval_mode=retrieval_mode, enable_rerank=enable_rerank)
        runtime_trace.setdefault("tool_events", []).append(
            {
                "tool_name": "summarize_sources",
                "input": {"query": query},
                "retrieval_trace": retrieval_trace,
            }
        )
        payload = {
            "query": query,
            "source_count": len(docs),
            "sources": format_sources(docs),
            "summary_material": [
                {
                    "source": doc.metadata.get("source"),
                    "title_path": doc.metadata.get("title_path"),
                    "text": doc.page_content[:500],
                }
                for doc in docs
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    return StructuredTool.from_function(
        func=summarize_sources,
        name="summarize_sources",
        description="当用户要求总结某个制度、产品或资料时调用，返回多个来源的摘要材料。",
        args_schema=SummarizeSourcesInput,
    )


def create_compare_sources_tool(
    retriever: KnowledgeBaseRetriever,
    runtime_trace: dict[str, Any],
    retrieval_mode: str | None = None,
    enable_rerank: bool | None = None,
) -> StructuredTool:
    """创建资料对比工具。

    当用户问“两个制度有什么区别”“A 模块和 B 模块差异是什么”时，
    Agent 可以用这个工具拿到多个来源的原文证据，再组织成对比答案。
    """

    def compare_sources(query: str) -> str:
        docs, retrieval_trace = retriever.search(query, retrieval_mode=retrieval_mode, enable_rerank=enable_rerank)
        runtime_trace.setdefault("tool_events", []).append(
            {
                "tool_name": "compare_sources",
                "input": {"query": query},
                "retrieval_trace": retrieval_trace,
            }
        )
        payload = {
            "query": query,
            "comparison_instruction": "请按来源逐条比较共同点、差异点和证据不足处。",
            "sources": [
                {
                    "source": doc.metadata.get("source"),
                    "title_path": doc.metadata.get("title_path"),
                    "chunk_id": doc.metadata.get("chunk_id"),
                    "text": doc.page_content,
                }
                for doc in docs
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    return StructuredTool.from_function(
        func=compare_sources,
        name="compare_sources",
        description="当用户要求比较多个制度、产品模块或资料差异时调用，返回可对比的证据列表。",
        args_schema=CompareSourcesInput,
    )
