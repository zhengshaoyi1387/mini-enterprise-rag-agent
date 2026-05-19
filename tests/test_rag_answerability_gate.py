from __future__ import annotations

from mini_rag.capabilities.rag.verifier import RagAnswerabilityGate, is_supporting_source


def test_unrelated_retrieved_source_is_not_supporting_evidence() -> None:
    task = {"query": "出差报销回来要注意什么", "objective": "说明出差报销注意事项"}
    source = {
        "source": "data/kbs/hr/hr_faq.md",
        "title_path": "HR > 薪酬 FAQ",
        "preview": "工资发放、薪酬保密、绩效奖金和社保公积金相关问答。",
    }

    assert is_supporting_source(source, task) is False


def test_related_travel_reimbursement_source_is_supporting_evidence() -> None:
    task = {"query": "出差报销回来要注意什么", "objective": "说明出差报销注意事项"}
    source = {
        "source": "data/kbs/finance/finance_policy.md",
        "title_path": "财务制度 > 差旅报销",
        "preview": "员工出差结束后应在 7 个工作日内提交差旅报销申请，并上传发票和行程单。",
    }

    assert is_supporting_source(source, task) is True


def test_short_chinese_policy_query_accepts_matching_finance_source() -> None:
    task = {"query": "公司报销制度", "objective": "介绍公司的报销制度"}
    source = {
        "kb_id": "finance",
        "source": "finance/finance_01_reimbursement_travel_procurement_2026.md",
        "title_path": "报销、差旅与采购制度 2026 > 关键规则与阈值",
        "preview": "费用报销需提交真实发票、审批单和差旅行程单，采购报销按预算规则执行。",
    }

    assert is_supporting_source(source, task) is True


def test_low_rerank_score_is_not_supporting_even_with_overlap() -> None:
    task = {"query": "出差报销回来要注意什么"}
    source = {
        "source": "finance.md",
        "title_path": "差旅报销",
        "preview": "差旅报销材料说明。",
        "rerank_score": 0.12,
    }

    assert is_supporting_source(source, task) is False


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
