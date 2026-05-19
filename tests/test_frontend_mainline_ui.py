from __future__ import annotations

from pathlib import Path


FRONTEND = Path("frontend/index.html")


def read_frontend() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def test_frontend_exposes_mainline_progress_ui() -> None:
    html = read_frontend()

    assert "正在理解问题" in html
    assert "生成执行计划" in html
    assert "执行任务" in html
    assert "生成最终回答" in html
    assert 'id="runDock"' not in html
    assert 'id="runSteps"' not in html
    assert "renderRunDock" not in html
    assert "updateLiveProgress" in html


def test_frontend_renders_mainline_log_in_details_not_raw_debug_by_default() -> None:
    html = read_frontend()

    assert 'data-tab="mainline"' in html
    assert 'id="mainlineBox"' in html
    assert "主线日志" in html
    assert "renderMainlineLog" in html
    assert "final.mainline_log" in html
    assert "debug-pill" in html


def test_frontend_has_polished_ai_chat_surfaces() -> None:
    html = read_frontend()

    assert "hero-surface" in html
    assert "assistant-thinking" in html
    assert "thinking-wave" in html
    assert "app-shell" in html
    assert "data-prompt=\"我明天有会议吗？如果有，出差报销回来要注意什么？\"" in html


def test_frontend_uses_warm_claude_like_design_tokens() -> None:
    html = read_frontend()

    assert "--bg: #faf8f3" in html
    assert "--surface:" in html
    assert "--surface-soft:" in html
    assert "--radius-lg:" in html
    assert "--shadow-soft:" in html
    assert "--sidebar: #111111" not in html
    assert "background: var(--sidebar);" not in html


def test_frontend_moves_header_actions_into_more_menu() -> None:
    html = read_frontend()

    assert 'id="moreBtn"' in html
    assert 'id="moreMenu"' in html
    assert 'class="top-more-menu hidden"' in html
    assert 'data-menu-action="admin"' in html
    assert 'data-menu-action="regenerate"' in html
    assert 'data-menu-action="export"' in html
    assert 'data-menu-action="details"' in html
    assert 'data-menu-action="clear"' in html


def test_frontend_collapses_debug_noise_and_renders_readable_artifacts() -> None:
    html = read_frontend()

    assert "renderExecutionSummary" in html
    assert "mainline-toggle" in html
    assert "已完成" in html
    assert "调用工具" in html
    assert "引用来源" in html
    assert "source-collapse" in html
    assert "shortTraceId" in html
    assert "trace_id ? `<span class=\"pill gray\">${escapeHtml(final.trace_id)}</span>`" not in html


def test_frontend_permission_drawer_has_lightweight_tabs_and_cards() -> None:
    html = read_frontend()

    assert "permission-drawer" in html
    assert "管理用户角色、知识库导入和索引状态" in html
    assert 'data-admin-tab="users"' in html
    assert 'data-admin-tab="kbs"' in html
    assert 'data-admin-tab="system"' in html
    assert "user-card-list" in html
    assert "new-user-panel" in html
    assert "kb-manager-card" in html


def test_frontend_login_is_product_entry_not_plain_form() -> None:
    html = read_frontend()

    assert "login-product-shell" in html
    assert "企业知识库与工具 Agent 演示系统" in html
    assert "Agentic RAG" in html
    assert "Tool Calling" in html
    assert "Permission-aware KB" in html


def test_frontend_waiting_state_is_compact_and_not_chain_explainer() -> None:
    html = read_frontend()

    assert "thinkingStatusText" in html
    assert "我会沿着 TimeContext" not in html
    assert "TimeContext → Planner → TimeResolver" not in html
    assert "thinking-copy" not in html
    assert "mini-progress-line" not in html


def test_frontend_streaming_tokens_patch_message_without_full_rerender() -> None:
    html = read_frontend()

    token_branch = html.split("if (event.event === 'token')", 1)[1].split("} else if (event.event === 'status')", 1)[0]
    assert "updateAssistantMessageDom(assistant)" in token_branch
    assert "renderMessages()" not in token_branch
    assert "data-message-index" in html
    assert "thinkingText" in html
