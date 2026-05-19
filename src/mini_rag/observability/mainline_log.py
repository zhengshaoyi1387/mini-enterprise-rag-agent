from __future__ import annotations

from typing import Any


MAX_DETAIL_CHARS = 180


def _clean_text(value: Any, *, max_chars: int = MAX_DETAIL_CHARS) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def append_mainline_step(
    state: dict[str, Any],
    *,
    stage: str,
    title: str,
    summary: str,
    details: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Append one compact, human-readable mainline step to state.

    This is the reader-facing layer. Debug trace fields such as prompts,
    raw tool results, full chunks and LLM IO stay in the existing trace.
    """

    log = state.setdefault("mainline_log", [])
    step = {
        "step": len(log) + 1,
        "stage": str(stage),
        "title": _clean_text(title, max_chars=80),
        "summary": _clean_text(summary, max_chars=240),
        "details": [_clean_text(item) for item in (details or []) if _clean_text(item)],
    }
    log.append(step)
    state["mainline_log_text"] = render_mainline_log(log)
    return step


def render_mainline_log(log: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None) -> str:
    lines: list[str] = []
    for index, item in enumerate(log or [], start=1):
        title = _clean_text(item.get("title"), max_chars=80)
        summary = _clean_text(item.get("summary"), max_chars=240)
        lines.append(f"{index}. {title}：{summary}")
        for detail in item.get("details") or []:
            lines.append(f"   - {_clean_text(detail)}")
    return "\n".join(lines)


def summarize_runtime_context(state: dict[str, Any]) -> tuple[str, list[str]]:
    runtime = state.get("runtime_context") if isinstance(state.get("runtime_context"), dict) else {}
    time_context = runtime.get("time_context_result") if isinstance(runtime.get("time_context_result"), dict) else state.get("time_context_result") or {}
    allowed_kbs = runtime.get("allowed_kbs") or state.get("allowed_kbs") or []
    current = str(time_context.get("current_date") or "")
    weekday = str(time_context.get("weekday_zh") or time_context.get("weekday") or "")
    details = [
        f"用户：{state.get('user_id') or runtime.get('user_id') or 'anonymous'}",
        f"用户角色：{state.get('role') or runtime.get('role') or 'unknown'}",
        f"可访问知识库：{', '.join(str(kb) for kb in allowed_kbs) if allowed_kbs else '无'}",
        f"当前时间：{current} {weekday}".strip(),
    ]
    return "已识别用户身份、权限、可访问知识库和当前时间。", details


def summarize_plan(state: dict[str, Any]) -> tuple[str, list[str]]:
    plan = state.get("execution_plan") if isinstance(state.get("execution_plan"), dict) else {}
    tasks = [task for task in plan.get("tasks") or [] if isinstance(task, dict)]
    intent = str((state.get("raw_plan") or {}).get("overall_intent") or state.get("intent") or state.get("route") or "unknown")
    details = [f"overall_intent：{intent}", f"任务数量：{len(tasks)}"]
    for task in tasks:
        kind = str(task.get("kind") or "")
        tool = str(task.get("tool") or task.get("tool_name") or "")
        action = str(task.get("action") or (task.get("tool_input") or {}).get("action") or "")
        query = str(task.get("query") or task.get("rag_query") or "")
        parts = [f"{task.get('task_id') or '?'}：kind={kind}"]
        if tool:
            parts.append(f"tool={tool}")
        if action:
            parts.append(f"action={action}")
        if query:
            parts.append(f"query={_clean_text(query, max_chars=80)}")
        details.append("，".join(parts))
    return f"Planner 生成了 {len(tasks)} 个任务，主意图为 {intent}。", details


def summarize_time_resolution(state: dict[str, Any]) -> tuple[str, list[str]]:
    facts = [fact for fact in state.get("resolved_time_facts") or [] if isinstance(fact, dict)]
    if not facts:
        return "本轮没有需要解析的相对时间。", []
    details: list[str] = []
    for fact in facts:
        expr = str(fact.get("time_expression") or "")
        items = fact.get("items") or []
        resolved = []
        for item in items:
            if not isinstance(item, dict):
                continue
            start = str(item.get("start_date") or "")
            end = str(item.get("end_date") or start)
            weekday = str(item.get("weekday_zh") or "")
            resolved.append(f"{start}" if start == end else f"{start} 至 {end}")
            if weekday:
                resolved[-1] = f"{resolved[-1]} {weekday}"
        details.append(f"{expr} -> {'；'.join(resolved) if resolved else '未解析'}")
    return "已把相对时间解析为工具可消费的绝对日期或日期范围。", details


def summarize_validation(state: dict[str, Any]) -> tuple[str, list[str]]:
    validation = state.get("plan_validation") if isinstance(state.get("plan_validation"), dict) else {}
    executable = validation.get("executable_tasks") or []
    blocked = validation.get("blocked_tasks") or []
    clarification = validation.get("clarification_tasks") or []
    details = [
        f"executable_tasks：{len(executable)}",
        f"blocked_tasks：{len(blocked)}",
        f"clarification_tasks：{len(clarification)}",
    ]
    for task in list(blocked)[:3] + list(clarification)[:3]:
        if not isinstance(task, dict):
            continue
        issue = task.get("_validation_issue") if isinstance(task.get("_validation_issue"), dict) else {}
        message = issue.get("message") or issue.get("code") or "需要进一步处理"
        details.append(f"{task.get('task_id') or '?'}：{message}")
    return "已完成权限、schema、日期和写操作安全校验。", details


def summarize_react_execution(state: dict[str, Any]) -> tuple[str, list[str]]:
    results = [item for item in state.get("task_results") or [] if isinstance(item, dict)]
    if not results:
        status = str(state.get("react_status") or "success")
        return f"ReAct 执行状态：{status}；本轮没有需要调用工具或检索的任务。", [f"react_status：{status}"]
    details: list[str] = []
    for result in results:
        kind = str(result.get("kind") or "")
        status = str(result.get("status") or "")
        if kind == "rag":
            queries = result.get("executed_queries") or ([result.get("query")] if result.get("query") else [])
            judgments = [item for item in result.get("evidence_judgments") or [] if isinstance(item, dict)]
            latest = judgments[-1] if judgments else {}
            sufficient = "充分" if latest.get("answerable") else "不足"
            reflect = "已触发" if result.get("retry_decision") or len(queries) > 1 else "未触发"
            supporting_count = len(result.get("sources") or [])
            details.append(
                f"{result.get('task_id') or '?'}：RAG，状态={status}，检索次数：{len(queries)}，"
                f"Evidence Judge：{sufficient}，RAG Reflect：{reflect}，supporting_sources：{supporting_count}"
            )
        else:
            tool = str(result.get("tool_name") or result.get("tool") or "")
            action = str(result.get("action") or "")
            count = _tool_result_count(result.get("tool_result"))
            suffix = f"，返回数量：{count}" if count is not None else ""
            details.append(f"{result.get('task_id') or '?'}：tool={tool}，action={action or '*'}，状态={status}{suffix}")
    return f"已执行 {len(results)} 个任务，当前执行状态为 {state.get('react_status') or 'unknown'}。", details


def summarize_answer(state: dict[str, Any]) -> tuple[str, list[str]]:
    packet = state.get("answer_packet") if isinstance(state.get("answer_packet"), dict) else {}
    task_results = [item for item in state.get("task_results") or [] if isinstance(item, dict)]
    details = [f"回答策略：{(state.get('answer_policy') or {}).get('strategy') or 'unknown'}", f"使用任务结果数量：{len(task_results)}"]
    rag_report = state.get("rag_answerability") if isinstance(state.get("rag_answerability"), dict) else {}
    if rag_report and not rag_report.get("answerable", True):
        details.append("因 supporting sources 不足，最终按证据不足处理。")
    elif any(item.get("kind") == "rag" for item in task_results):
        details.append(f"最终使用 supporting_sources：{len(state.get('sources') or [])}")
    status = packet.get("status") or (state.get("completion_assessment") or {}).get("execution_status") or "unknown"
    return f"最终回答已基于结构化任务结果生成，状态为 {status}。", details


def summarize_memory(state: dict[str, Any]) -> tuple[str, list[str]]:
    session_id = state.get("session_id")
    memory = state.get("memory_update") if isinstance(state.get("memory_update"), dict) else {}
    if not session_id:
        return "本轮没有需要写入长期记忆的信息。", ["原因：未提供 session_id"]
    if not memory:
        return "本轮没有需要写入长期记忆的信息。", ["原因：memory_update 为空"]
    return "已将本轮问答摘要写入会话记忆。", [
        f"session_id：{session_id}",
        f"topic：{memory.get('topic') or '未提取'}",
        f"entities：{', '.join(str(item) for item in memory.get('entities') or []) if memory.get('entities') else '无'}",
    ]


def _tool_result_count(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in ("events", "records", "items", "results", "rows"):
        if isinstance(value.get(key), list):
            return len(value[key])
    if isinstance(value.get("event"), dict):
        return 1
    return None
