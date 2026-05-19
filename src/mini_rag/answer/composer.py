from __future__ import annotations

from typing import Any

from mini_rag.answer.formatters import format_tool_result
from mini_rag.answer.templates import (
    clarification_required_direct_answer,
    permission_required_direct_answer,
)
from mini_rag.security.permissions import normalize_role


def _task_result_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    tool_result = result.get("tool_result")
    return tool_result if isinstance(tool_result, dict) else {}


def _format_tool_task(result: dict[str, Any], context: str = "") -> str:
    summary = str(result.get("result_summary") or "").strip()
    status = str(result.get("status") or "").strip().lower()
    tool_result = _task_result_tool_result(result)
    tool_name = str(result.get("tool_name") or "").strip()

    if status in {"skipped", "needs_clarification", "refused", "blocked"} and summary:
        return summary
    if tool_name and tool_result:
        tool_result = dict(tool_result)
        tool_result.setdefault("action", result.get("action"))
        task_context = "\n".join(str(value or "") for value in (context, result.get("objective"), result.get("query")))
        return format_tool_result(tool_name, tool_result, context=task_context)
    if summary:
        return summary
    return ""


def _tool_results_only(task_results: list[dict[str, Any]]) -> bool:
    if not task_results:
        return False
    for result in task_results:
        if str(result.get("kind") or "").lower() == "rag":
            return False
        if result.get("sources") or result.get("candidate_sources"):
            return False
    return True


def _calendar_write_permission_notice(state: dict[str, Any], task_results: list[dict[str, Any]]) -> str:
    role = normalize_role(state.get("role"))
    if role == "admin":
        return ""
    has_calendar_context = any(
        result.get("tool_name") == "manage_company_calendar"
        for result in task_results
        if isinstance(result, dict)
    )
    if not has_calendar_context:
        return ""
    text = str(state.get("question") or "") + "\n" + str(state.get("standalone_query") or "")
    if any(token in text.lower() for token in ("删除", "修改", "更新", "新增", "创建", "delete", "update", "create")):
        return "你没有权限修改公司日程，也无权执行删除、更新或新增操作；只有 admin 可以修改公司日程。"
    return ""


def _event_id_sentinel_safety_explanation(state: dict[str, Any]) -> str | None:
    text = f"{state.get('question') or ''}\n{state.get('standalone_query') or ''}".lower()
    if "event_id" not in text:
        return None
    has_sentinel = any(token in text for token in ("event_id=all", "event_id = all", "event_id=multiple", "event_id_from", "event_id=*"))
    asks_reason = any(token in text for token in ("为什么", "不能", "不允许", "why", "cannot"))
    if not has_sentinel or not asks_reason:
        return None
    return (
        "不能直接使用 event_id=all 执行日程删除或更新。真实写工具只接受具体的 EVT-YYYYMMDD-0001 这类单个 event_id；"
        "all、multiple、event_id_from_x 这类占位符必须先经过查询和 selector 解析，确认 0 个、1 个、多个或“全部/所有”的明确范围。"
        "在目标未解析成真实 event_id 前，我不会执行删除。"
    )


def compose_template_answer(state: dict[str, Any]) -> str | None:
    """Compose deterministic answers that must not call the answer LLM."""

    route = str(state.get("route") or "direct")
    intent = str(state.get("intent") or "")
    safety_explanation = _event_id_sentinel_safety_explanation(state)
    if safety_explanation:
        return safety_explanation
    if route == "reject":
        return str(state.get("final_answer") or "抱歉，这个请求存在安全风险，我不能执行。")
    if route == "direct" and intent == "smalltalk":
        return str(state.get("final_answer") or "你好，我是企业知识库助手。你可以问我公司制度、考勤、公司日程等问题。")
    if route == "direct" and intent == "permission_required":
        return str(state.get("final_answer") or permission_required_direct_answer(state))
    if route == "direct" and intent in {"need_clarification", "clarification_required"}:
        return str(state.get("final_answer") or clarification_required_direct_answer(state))

    if route != "tool":
        return None

    existing_answer = str(state.get("final_answer") or "").strip()
    if existing_answer:
        return existing_answer

    task_results = [item for item in (state.get("task_results") or []) if isinstance(item, dict)]
    if not task_results:
        current_context = state.get("current_tool_context") if isinstance(state.get("current_tool_context"), dict) else {}
        summary = str(current_context.get("result_summary") or "").strip()
        return summary or None

    if not _tool_results_only(task_results):
        return None

    messages = []
    answer_context = "\n".join(str(value or "") for value in (state.get("question"), state.get("standalone_query")))
    for result in task_results:
        message = _format_tool_task(result, context=answer_context)
        if message and message not in messages:
            messages.append(message)
    permission_notice = _calendar_write_permission_notice(state, task_results)
    if permission_notice and permission_notice not in messages:
        messages.append(permission_notice)
    if not messages:
        return None
    return "\n".join(messages)
