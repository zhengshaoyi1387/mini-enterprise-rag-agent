from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests
from langchain_core.documents import Document


class QwenReranker:
    """DashScope Qwen rerank 封装，失败时由调用方继续使用原排序。

    RAG 里通常分两步：
    1. 召回：先用向量/BM25 快速找一批候选 chunk。
    2. 重排：让 reranker 判断这些 chunk 和问题到底谁更相关。

    rerank 是“提高证据排序质量”的步骤，但它依赖外部 API。
    所以这里专门做了降级：API 超时、报错、返回异常时，不让整个问答失败，
    而是回退到 RRF 融合后的原始顺序，并把错误写进 trace。
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        endpoint: str,
        http_post: Callable[..., Any] | None = None,
    ):
        # http_post 支持依赖注入，测试时可以传一个假的函数，
        # 这样不用真的请求 DashScope，也能验证失败降级逻辑。
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.http_post = http_post or requests.post

    def rerank(self, query: str, docs: list[Document], top_n: int, trace: dict) -> list[Document]:
        """对候选文档重排，并把输入数量、模型名、错误信息写入 trace。"""
        trace["rerank_enabled"] = True
        trace["rerank_model"] = self.model
        trace["rerank_input_count"] = len(docs)
        if not docs:
            trace["rerank_output_count"] = 0
            return []

        try:
            # DashScope rerank API 的核心输入：
            # - query：用户问题。
            # - documents：候选 chunk 文本列表。
            # - top_n：希望返回前多少条。
            response = self.http_post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "query": query,
                    "documents": [doc.page_content for doc in docs],
                    "top_n": min(top_n, len(docs)),
                    "instruct": "Given a web search query, retrieve relevant passages that answer the query.",
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            # 官方 DashScope 返回通常是 output.results；
            # 这里保留 payload["results"] fallback，方便兼容测试替身或未来轻微变化。
            results = payload.get("output", {}).get("results", payload.get("results", []))
            ranked_docs: list[Document] = []
            for rank, item in enumerate(results, start=1):
                # API 返回 index，表示原始 documents 列表里的第几个 chunk。
                # 我们用这个 index 找回原始 Document，再把 rerank 分数写进 metadata。
                index = int(item.get("index", -1))
                if index < 0 or index >= len(docs):
                    continue
                doc = docs[index]
                metadata = dict(doc.metadata or {})
                metadata.update(
                    {
                        "rank": rank,
                        "rerank_score": float(item.get("relevance_score", item.get("score", 0.0))),
                        "retrieval_channel": metadata.get("retrieval_channel", "hybrid") + "+qwen_rerank",
                    }
                )
                ranked_docs.append(Document(page_content=doc.page_content, metadata=metadata))
            trace["rerank_output_count"] = len(ranked_docs)
            # 如果 API 正常返回但 results 为空，仍然回退到原顺序，避免给 LLM 空证据。
            return ranked_docs or docs[:top_n]
        except Exception as exc:
            # 企业项目里外部模型调用一定要有降级策略。
            # 这里保留错误信息给 trace，便于排查是网络、鉴权还是 API 返回问题。
            trace["rerank_error"] = str(exc)
            trace["rerank_output_count"] = min(top_n, len(docs))
            return docs[:top_n]
