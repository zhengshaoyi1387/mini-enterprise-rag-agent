from __future__ import annotations

from langchain_core.documents import Document

from mini_rag.retrieval.retriever import KnowledgeBaseRetriever


def test_explicit_document_title_boosts_matching_source() -> None:
    docs = [
        Document(
            page_content="病假连续超过 3 个工作日需上传医疗证明。",
            metadata={"rank": 1, "source": "hr/hr_03_compensation_benefits_faq.txt", "title_path": "薪酬福利 FAQ"},
        ),
        Document(
            page_content="# 考勤与休假管理制度 2026\n病假连续超过 3 个工作日需上传医疗证明。",
            metadata={"rank": 2, "source": "hr/hr_01_attendance_leave_policy_2026.md", "title_path": "考勤与休假管理制度 2026"},
        ),
    ]

    ranked = KnowledgeBaseRetriever._boost_explicit_source_matches("根据《考勤与休假管理制度 2026》回答", docs)

    assert ranked[0].metadata["source"] == "hr/hr_01_attendance_leave_policy_2026.md"
    assert ranked[0].metadata["explicit_source_boost"] == 1.0
