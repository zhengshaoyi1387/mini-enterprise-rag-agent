from __future__ import annotations

import pytest

from mini_rag.security.permissions import (
    assert_tool_permission,
    can_access_endpoint,
    can_use_tool,
    normalize_role,
)


def test_normalize_unknown_role_to_guest() -> None:
    assert normalize_role("hacker") == "guest"
    assert normalize_role(None) == "user"


def test_endpoint_permissions() -> None:
    assert can_access_endpoint("guest", "chat") is True
    assert can_access_endpoint("user", "trace") is False
    assert can_access_endpoint("admin", "trace") is True


def test_tool_permissions() -> None:
    assert can_use_tool("guest", "search_knowledge_base") is True
    assert can_use_tool("guest", "compare_sources") is False
    assert can_use_tool("user", "compare_sources") is True
    assert can_use_tool("admin", "run_eval") is True


def test_assert_tool_permission_raises_on_forbidden_tool() -> None:
    with pytest.raises(PermissionError):
        assert_tool_permission("guest", "compare_sources")
