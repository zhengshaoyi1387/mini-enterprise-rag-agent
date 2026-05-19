from __future__ import annotations

from mini_rag.capabilities.rag.verifier import RagAnswerabilityGate, answer_has_sources_for_rag


def test_answerability_gate_refuses_when_all_rag_tasks_lack_support() -> None:
    state = {
        "route": "rag",
        "question": "出差报销回来要注意什么？",
        "task_results": [
            {
                "task_id": "policy",
                "kind": "rag",
                "status": "empty",
                "objective": "说明出差报销注意事项",
                "query": "出差报销回来要注意什么",
                "sources": [],
                "candidate_sources": [
                    {
                        "source": "data/kbs/hr/hr_faq.md",
                        "title_path": "HR > 薪酬 FAQ",
                        "preview": "工资发放、薪酬保密、绩效奖金和社保公积金相关问答。",
                    }
                ],
            }
        ],
        "sources": [],
    }

    report = RagAnswerabilityGate().evaluate(state)

    assert report.answerable is False
    assert report.status == "insufficient_evidence"
    assert "当前可访问知识库未找到明确依据" in report.message


def test_answerability_gate_accepts_llm_judged_supporting_sources() -> None:
    state = {
        "route": "rag",
        "task_results": [
            {
                "task_id": "policy",
                "kind": "rag",
                "status": "ok",
                "sources": [{"source": "finance/finance_01_reimbursement_travel_procurement_2026.md"}],
                "candidate_sources": [{"source": "hr/hr_faq.md"}],
                "evidence_judgments": [{"answerable": True, "supporting_source_ids": ["s1"]}],
            }
        ],
        "sources": [{"source": "finance/finance_01_reimbursement_travel_procurement_2026.md"}],
    }

    report = RagAnswerabilityGate().evaluate(state)

    assert report.answerable is True
    assert report.supported_task_ids == ("policy",)


def test_answerability_gate_does_not_count_candidate_sources() -> None:
    state = {
        "route": "rag",
        "task_results": [
            {
                "task_id": "policy",
                "kind": "rag",
                "status": "empty",
                "sources": [],
                "candidate_sources": [{"source": "finance/finance_01_reimbursement_travel_procurement_2026.md"}],
                "evidence_judgments": [{"answerable": False}],
            }
        ],
        "sources": [],
    }

    report = RagAnswerabilityGate().evaluate(state)

    assert report.answerable is False
    assert report.unsupported_task_ids == ("policy",)


def test_answer_has_sources_for_rag_requires_real_sources() -> None:
    assert answer_has_sources_for_rag({"route": "rag", "final_answer": "答案 来源：x", "sources": []}) is False
    assert answer_has_sources_for_rag({"route": "rag", "final_answer": "答案 来源：x", "sources": [{"source": "x"}]}) is True
