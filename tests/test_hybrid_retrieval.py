from langchain_core.documents import Document

from mini_rag.retrieval.hybrid import bm25_rank, reciprocal_rank_fusion, tokenize_for_search


def test_tokenize_for_search_handles_chinese_and_ascii_terms():
    tokens = tokenize_for_search("智能客服平台 password reset")

    assert "智能" in tokens or "智能客服" in tokens or "客服" in tokens
    assert "password" in tokens
    assert "reset" in tokens


def test_bm25_rank_prefers_matching_document():
    docs = [
        Document(page_content="报销制度要求发票和审批单", metadata={"chunk_id": "a"}),
        Document(page_content="智能客服平台包含知识库检索模块", metadata={"chunk_id": "b"}),
    ]

    ranked = bm25_rank("智能客服知识库", docs, top_k=2)

    assert ranked[0][0].metadata["chunk_id"] == "b"
    assert ranked[0][1] > ranked[1][1]


def test_reciprocal_rank_fusion_merges_ranked_channels():
    fused = reciprocal_rank_fusion(
        [
            [("a", 0.2), ("b", 0.1)],
            [("b", 3.0), ("c", 2.0)],
        ],
        k=60,
    )

    assert fused[0][0] == "b"
    assert {item[0] for item in fused} == {"a", "b", "c"}

