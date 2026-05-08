from __future__ import annotations

from mini_rag.ingestion.kb_config import infer_kb_id_from_source, list_knowledge_bases
from mini_rag.security.permissions import assert_can_access_kbs, get_allowed_kbs
from mini_rag.tools.office_tools import build_default_tool_registry, select_office_tool_by_rule


def test_kb_catalog_and_inference() -> None:
    assert any(item["kb_id"] == "finance" for item in list_knowledge_bases())
    assert infer_kb_id_from_source("data/kbs/finance/报销制度.md") == "finance"
    assert infer_kb_id_from_source("data/raw/03_财务报销制度.md") == "finance"
    assert infer_kb_id_from_source("data/raw/02_人事考勤制度.md") == "hr"


def test_role_kb_permissions_are_kb_level() -> None:
    assert "finance" in get_allowed_kbs("admin")
    assert "finance" in get_allowed_kbs("finance")
    assert "finance" not in get_allowed_kbs("employee")
    assert_can_access_kbs("finance", ["finance"])
    try:
        assert_can_access_kbs("employee", ["finance"])
    except PermissionError:
        pass
    else:
        raise AssertionError("employee should not access finance kb")


def test_office_tool_registry_returns_drafts_only() -> None:
    registry = build_default_tool_registry()
    assert select_office_tool_by_rule("帮我写一份周报") == "generate_weekly_report"
    result = registry.invoke("create_it_ticket", {"query": "电脑无法联网"})
    assert "工单草稿" in result["content"]
    assert "不会真实提交" in result["content"]


def test_policy_lookup_questions_do_not_trigger_reimbursement_tool() -> None:
    assert select_office_tool_by_rule("报销的时限是多少") is None
    assert select_office_tool_by_rule("差旅报销需要哪些材料？") is None
    assert select_office_tool_by_rule("发票抬头有什么要求？") is None
    assert select_office_tool_by_rule("这笔住宿超标能不能报销？") == "check_reimbursement_rule"
    assert select_office_tool_by_rule("帮我判断这张发票是否可以报销") == "check_reimbursement_rule"
