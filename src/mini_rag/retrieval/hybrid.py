from __future__ import annotations

import math
import re
from collections import Counter

from langchain_core.documents import Document


def tokenize_for_search(text: str) -> list[str]:
    """中英文混合检索分词。

    有 jieba 时使用 jieba；没有时退化为中文 2-gram + 英文单词，保证测试和基础功能可用。
    """
    # 关键词检索和向量检索的关注点不同：
    # - 向量检索擅长“语义相近”，例如“报销”能匹配“费用申请”。
    # - BM25 擅长“关键词精确出现”，例如产品名、制度名、英文参数名。
    # 所以这里要先把文本切成适合关键词匹配的 token。
    text = text.lower()
    try:
        import jieba

        tokens = [token.strip() for token in jieba.cut(text) if token.strip()]
    except Exception:
        tokens = []

    # 英文、数字、下划线按单词保留，适合匹配 API 名称、参数名、产品代号。
    ascii_tokens = re.findall(r"[a-z0-9_]+", text)

    # 如果没有 jieba，中文直接按单字很容易太碎。
    # 这里额外构造中文 2-gram，例如“智能客服”会得到“智能”“能客”“客服”，
    # 虽然不如专业分词完美，但能保证没有 jieba 时仍有基本召回能力。
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    chinese_bigrams = ["".join(chinese_chars[i : i + 2]) for i in range(max(0, len(chinese_chars) - 1))]
    return [token for token in tokens + ascii_tokens + chinese_bigrams if token]


def bm25_rank(query: str, docs: list[Document], top_k: int) -> list[tuple[Document, float]]:
    """轻量 BM25 排序，用于企业 RAG 的关键词召回通道。

    新手理解：
    BM25 可以理解成“更聪明的关键词匹配分数”。
    如果用户问“报销发票”，包含这些词的文档会得分更高；
    如果某个词在所有文档里都很常见，它的区分度就会降低。
    """
    if not docs:
        return []

    # 先把所有候选文档和 query 都切成 token，后面的公式都基于 token 统计。
    tokenized_docs = [tokenize_for_search(doc.page_content) for doc in docs]
    query_terms = tokenize_for_search(query)

    # avgdl 是平均文档长度。BM25 会用它修正文档长短的影响：
    # 长文档出现关键词更多是正常现象，不应该天然占便宜太多。
    avgdl = sum(len(tokens) for tokens in tokenized_docs) / max(1, len(tokenized_docs))
    doc_freq: Counter[str] = Counter()
    for tokens in tokenized_docs:
        # doc_freq 统计“某个词出现在多少篇文档里”，不是出现多少次。
        # 它用于计算 IDF：越少见的词，区分度越高。
        doc_freq.update(set(tokens))

    # k1 和 b 是 BM25 的常用经验参数：
    # - k1 控制词频增加带来的收益会不会很快饱和。
    # - b 控制文档长度归一化的强度。
    k1 = 1.5
    b = 0.75
    scored: list[tuple[Document, float]] = []
    for doc, tokens in zip(docs, tokenized_docs):
        counts = Counter(tokens)
        score = 0.0
        doc_len = len(tokens) or 1
        for term in query_terms:
            if term not in counts:
                continue
            # IDF：一个词越少见，越能说明文档和问题相关。
            idf = math.log(1 + (len(docs) - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            tf = counts[term]
            denom = tf + k1 * (1 - b + b * doc_len / max(avgdl, 1))
            score += idf * (tf * (k1 + 1) / denom)
        scored.append((doc, score))

    return sorted(scored, key=lambda item: item[1], reverse=True)[:top_k]


def reciprocal_rank_fusion(
    ranked_channels: list[list[tuple[str, float]]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """把多个召回通道的排名用 RRF 融合。

    RRF 的思想很简单：
    一个 chunk 如果在“向量检索”和“BM25 检索”里都排得靠前，就更可信。
    它不直接比较不同通道的原始分数，因为向量距离和 BM25 分数不是一个量纲。
    它只看“排名位置”，所以非常适合融合不同检索器。
    """
    scores: dict[str, float] = {}
    for channel in ranked_channels:
        for rank, (doc_id, _score) in enumerate(channel, start=1):
            # rank 越小，贡献越大。k 用来避免第一名分数过分夸张。
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)
