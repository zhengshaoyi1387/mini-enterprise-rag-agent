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


def create_search_knowledge_base_tool(
    retriever: KnowledgeBaseRetriever,
    runtime_trace: dict[str, Any],
    retrieval_mode: str | None = None,
    enable_rerank: bool | None = None,
) -> StructuredTool:
    """创建 search_knowledge_base 工具。

    Legacy create_agent 路径只保留这个核心 RAG 工具；查询改写、资料总结和资料对比已经下线，
    在 LangGraph 主链路中由 understand_query、plan_retrieval 和最终回答节点承担。
    """

    def search_knowledge_base(query: str) -> str:
        """检索企业知识库，返回与问题相关的证据。"""
        docs, retrieval_trace = retriever.search(
            query,
            retrieval_mode=retrieval_mode,
            enable_rerank=enable_rerank,
        )
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
