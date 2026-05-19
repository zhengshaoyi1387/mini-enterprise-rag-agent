from __future__ import annotations

from mini_rag.ingestion.kb_config import infer_kb_id_from_source, list_knowledge_bases
from mini_rag.security.permissions import assert_can_access_kbs, get_allowed_kbs
from mini_rag.tools.daily_tools import build_default_tool_registry


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


def test_daily_tool_registry_contains_real_business_tools_only() -> None:
    registry = build_default_tool_registry()
    names = {tool["name"] for tool in registry.list_tools()}
    assert names == {"search_knowledge_base", "get_current_datetime", "query_attendance_summary", "manage_company_calendar"}


def test_no_rule_based_daily_tool_selector_is_exported() -> None:
    import mini_rag.tools.daily_tools as daily_tools

    old_name = "select_" + "daily_" + "tool_" + "by_" + "rule"
    assert not hasattr(daily_tools, old_name)
