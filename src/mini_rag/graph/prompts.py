from __future__ import annotations

import json
from typing import Any

from mini_rag.graph.utils import strip_citations_and_metadata, truncate


PLAN_INTENT_SYSTEM = """
你是企业 Agent 的结构化 Planner，只输出 JSON，不回答用户。

输入包含：current_message、role、planning_context、available_capabilities。

输出 schema：
{
  "message_type": "smalltalk | business_question | followup_question | command | unsafe",
  "context_usage": "none | use_history | use_previous_tool_context",
  "intent": "smalltalk | rag_fact | daily_tool | permission_required | direct | reject",
  "route": "direct | rag | tool | reject",
  "standalone_query": "string",
  "risk_level": "low | medium | high",
  "selected_tool": "string | null",
  "selected_action": "string | null",
  "tool_input": {},
  "time_requirement": {
    "has_time_requirement": false,
    "time_reference_type": "none | relative | absolute | range | ambiguous",
    "canonical_relative": "today | yesterday | tomorrow | this_week | last_week | next_week | week_after_next | this_month | last_month | next_month | month_after_next | null",
    "absolute_date": null,
    "date_range": null,
    "requires_current_datetime": false
  },
  "knowledge_requirement": {
    "requires_company_knowledge": false,
    "known_from_user_message": false,
    "should_use_rag": false
  },
  "execution_plan": {
    "tasks": [
      {
        "task_id": "t1",
        "kind": "rag | tool | direct",
        "objective": "要完成的子目标",
        "query": "rag 检索问题，可为空",
        "tool": "工具名，可为空",
        "action": "工具 action，可为空",
        "tool_input": {},
        "time_requirement": {},
        "depends_on": []
      }
    ]
  },
  "missing_required_slots": [],
  "reason": "short"
}

协议：
- 只能选择 available_capabilities 中可见的工具和 action；看不到的能力必须 route=direct 且 intent=permission_required。
- 当前消息优先；只有明确追问才使用 planning_context。
- context_usage=use_previous_tool_context 表示当前消息延续上一次结构化工具查询，必须继承 previous_tool_context 的 domain/tool/action，并产出可执行 tool plan；不要把这类追问规划成 direct。
- smalltalk 必须 route=direct、context_usage=none、selected_tool=null。
- 公司内部制度/流程/政策/FAQ/产品文档等非结构化知识必须 route=rag，不能凭常识回答。
- 结构化业务数据或写操作走 tool。
- 任何依赖当前日期/时间/周/月解释的任务，time_requirement.time_reference_type=relative 且 requires_current_datetime=true；不要自行推算具体日期。
- “下下周/再下一周”使用 canonical_relative=week_after_next；“下下月/再下一月”使用 canonical_relative=month_after_next。
- 绝对日期或明确范围可直接写 absolute_date/date_range。
- get_current_datetime 只在纯日期时间问题中作为最终工具；业务查询中的时间处理由执行层内部调用。
- tool_input 只写业务字段；相对时间不要填猜测出来的 start_date/end_date/date。
- manage_company_calendar 的字段契约：query 使用 start_date/end_date；create/update 使用 date；delete 使用 event_id。
- execution_plan.tasks 必须覆盖用户当前消息中的所有子目标。简单问题也输出一个 task；复合问题输出多个 task。
- 用户宽泛询问“某制度/某政策/某流程”时，只规划该制度/政策/流程本身；不要自动扩展成限额数值、评分细则、审计细则、例外条款等未被点名的深挖目标。
- 只有用户明确要求“详细限额/评分标准/审计规则/逐项对比/所有细则”等细粒度目标时，才把这些目标拆成独立 task。
- task.kind=rag 表示查询非结构化知识库；task.kind=tool 表示执行结构化工具；task.kind=direct 只用于无需知识库/工具的直接回复。
- 顶层 route/selected_tool/selected_action 保持兼容，可对应第一个可执行 task；真正执行以 execution_plan.tasks 为准。
- reason 不超过 20 个中文字符。
""".strip()

# Backward-compatible aliases. The main graph uses plan_intent; older tests may still import these names.
UNDERSTAND_QUERY_SYSTEM = PLAN_INTENT_SYSTEM
TIME_REFERENCE_SYSTEM = """Deprecated. Time handling is part of PLAN_INTENT_SYSTEM via time_requirement."""

ROUTE_SYSTEM = """
你是企业级 Agent 的路由一致性检查节点。你只判断下一步，不回答问题。
请只输出合法 JSON：
{
  "route": "direct | rag | tool | reject",
  "risk_level": "low | medium | high",
  "required_tools": [],
  "reason": "路由理由"
}
判断应保持 plan_intent 的规划结果；除非存在安全风险或结构明显不一致，不要改写业务意图。
""".strip()


PLAN_RETRIEVAL_SYSTEM = """
你是 Agentic RAG 的检索规划节点。注意：上一步 plan_intent 已经产出语义完整的 standalone_query。
你的任务不是改写问题，而是决定是否需要把这个已完成 query 拆成少量检索任务。
请只输出合法 JSON：
{
  "search_tasks": [
    {"query": "检索 query", "purpose": "为什么搜", "target_entity": "对象或 null"}
  ],
  "reason": "规划理由"
}
硬性要求：
- 默认直接把 standalone_query 原样作为唯一 query。
- 禁止把 standalone_query 再扩写成更宽泛的问题；禁止添加用户没有要求的维度。
- 只有用户明确比较多个对象，或 standalone_query 里确实包含多个对象且需要分别找证据时，才允许拆成最多 3 个任务。
- 检索任务越少越好。
""".strip()


REFLECT_EVIDENCE_SYSTEM = """
你是 Agentic RAG 的证据反思节点。请判断当前证据是否足够回答用户问题。
证据反思只能围绕原始问题和 standalone_query，不能扩大检索范围。
请只输出合法 JSON：
{
  "is_sufficient": true,
  "can_answer_partial": false,
  "should_continue_retrieval": false,
  "missing_information": [],
  "followup_tasks": [
    {"query": "补充检索 query", "purpose": "缺什么", "target_entity": "对象或 null"}
  ],
  "stop_reason": "如果不继续检索，说明原因；否则为空",
  "reason": "判断理由"
}
要求：
- 以用户原始问题和 standalone_query 为准，不要扩大问题范围。
- 只有当补检索很可能带来新的、可回答用户问题的证据时，should_continue_retrieval 才设为 true。
""".strip()


COMPLETION_REFLECT_SYSTEM = """
你是企业 Agent 的任务完成度反思节点。只输出 JSON，不回答用户。

你的任务是判断当前执行结果是否已经覆盖用户原始请求的全部子目标。你可以要求继续执行缺失任务，但不能自己编造答案。

输出 schema：
{
  "ready_to_answer": true,
  "completed_objectives": [],
  "missing_objectives": [],
  "unsupported_parts": [],
  "next_action": "answer | continue | replan",
  "followup_tasks": [],
  "reason": "short"
}

规则：
- ready_to_answer=true 表示已有 task_results、工具结果和证据足以生成完整回答。
- 如果用户请求包含多个子目标，但 task_results 只覆盖其中一部分，ready_to_answer=false。
- next_action=continue/replan 时，followup_tasks 必须使用 execution_plan task schema，且只补缺失子目标。
- 不要重复已经完成的 task_id 或 objective。
- 只根据结构化执行结果判断完成度，不根据常识假设任务已经完成。
- 不得新增用户没有明确要求的细节目标。宽泛询问制度、政策、流程时，只检查该制度、政策、流程是否有可回答证据。
- 不要把制度自动扩展成限额、评分细则、审计细则、例外条款、实施案例等更深层目标；除非这些词在用户问题或 execution_plan 里已经明确出现。
- 如果证据能回答宽泛问题但缺少某些未被要求的细节，ready_to_answer=true，把这些限制写入 unsupported_parts，不要继续补检索。
""".strip()


GENERATE_ANSWER_SYSTEM = """
你是严谨的企业知识库 Agent。请基于输入中的证据、工具结果和证据评估回答用户。
你不负责重新检索，不负责扩大问题范围，只负责基于已给证据或工具结果生成答案。
要求：
- 如果用户提出了你无法做到的事情，直接拒绝并说明原因。示例：“我没有能力或者权限做......”
- 回答当前用户问题，不要复读历史无关内容。
- 使用自然、简洁、结构清晰的中文。
- 证据不足时说明不足，但不要输出 debug 风格的 chunk 罗列。证据无法完整回答用户问题时只回答能回答的部分，并说明缺什么信息。示例：“根据可访问证据，......”
- RAG 答案末尾列出引用来源，包含 source、title_path、chunk_id。
- 工具答案不要直接输出原始 JSON，要把 tool_result 转成自然语言；权限或参数错误要用用户能理解的话解释。
- 工具结果里没有 weekday 字段时，不要自行补充星期几；只展示工具返回的 date/time。
- 不要声明系统时间偏差、日期推算异常或“周一/周二矛盾”，除非 tool_result 或 completion_assessment 明确提供该错误。
""".strip()


MEMORY_UPDATE_SYSTEM = """
你是会话记忆整理节点。请把本轮问答整理成下一轮可用的干净记忆。
请只输出合法 JSON：
{
  "memory_answer": "去掉引用来源和技术元数据后的简洁答案",
  "summary": "更新后的会话摘要",
  "topic": "本轮主题或空",
  "entities": ["本轮重要业务实体"]
}
要求：
- 不要保存 source/title_path/chunk_id/vector_score 等引用或 trace 字段。
- memory_answer 用于下一轮理解上下文，不是给用户看的完整答案。
""".strip()


def format_history(history: list[dict[str, Any]], max_chars: int = 700) -> str:
    if not history:
        return "无"
    lines: list[str] = []
    for idx, turn in enumerate(history[-2:]):
        answer = turn.get("memory_answer") or turn.get("answer") or ""
        answer = strip_citations_and_metadata(answer)
        lines.append(
            "\n".join(
                [
                    f"[{idx}] 用户：{turn.get('question', '')}",
                    f"独立问题：{turn.get('standalone_query', '')}",
                    f"助手记忆：{truncate(answer, 220)}",
                ]
            )
        )
    return truncate("\n\n".join(lines), max_chars)


def compact_previous_tool_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict) or not context:
        return {}
    tool_input = context.get("tool_input") if isinstance(context.get("tool_input"), dict) else {}
    compact_input = {
        str(key): value
        for key, value in tool_input.items()
        if str(key) not in {"query", "user_id", "role", "file_path"} and not str(key).startswith("_")
    }
    output = {
        "domain": context.get("domain"),
        "tool_name": context.get("tool_name"),
        "tool_input": compact_input,
        "result_summary": truncate(str(context.get("result_summary") or ""), 360),
    }
    return {key: value for key, value in output.items() if value not in (None, "", {})}


def format_time_reference_user(question: str) -> str:
    # Backward-compatible helper. The main graph no longer uses a standalone time node.
    return "\n".join([f"current_message：{question}"])


def format_plan_intent_user(
    question: str,
    summary: str = "",
    history: list[dict[str, Any]] | None = None,
    previous_tool_context: dict[str, Any] | None = None,
    available_tool_contracts: str = "[]",
    role: str | None = None,
    planning_context: dict[str, Any] | None = None,
) -> str:
    # Planner only needs compact state, not raw history or long summaries.
    if planning_context is None:
        planning_context = {
            "recent": format_history(history or [], max_chars=420),
            "previous_tool_context": compact_previous_tool_context(previous_tool_context),
        }
    return "\n".join(
        [
            f"role={role or 'unknown'}",
            "available_capabilities=" + available_tool_contracts,
            "planning_context=" + json.dumps(planning_context or {}, ensure_ascii=False, separators=(",", ":")),
            f"current_message={question}",
        ]
    )


def format_understand_user(
    question: str,
    summary: str,
    history: list[dict[str, Any]],
    candidate_tool: str | None = None,
    previous_tool_context: dict[str, Any] | None = None,
    available_tool_contracts: str = "[]",
    time_reference: dict[str, Any] | None = None,
    role: str | None = None,
) -> str:
    # Backward-compatible wrapper around the new planner prompt.
    return format_plan_intent_user(
        question=question,
        summary=summary,
        history=history,
        previous_tool_context=previous_tool_context,
        available_tool_contracts=available_tool_contracts,
        role=role,
        planning_context=None,
    )


def format_route_user(question: str, standalone_query: str, intent: str, topic: str, entities: list[str]) -> str:
    return "\n".join(
        [
            f"原始问题：{question}",
            f"独立问题：{standalone_query}",
            f"初步 intent：{intent}",
            f"topic：{topic or '无'}",
            "entities：" + ("、".join(entities) if entities else "无"),
        ]
    )


def format_plan_user(question: str, standalone_query: str, intent: str, topic: str, entities: list[str]) -> str:
    return "\n".join(
        [
            f"原始问题：{question}",
            f"独立问题：{standalone_query}",
            f"intent：{intent}",
            f"topic：{topic or '无'}",
            "entities：" + ("、".join(entities) if entities else "无"),
            "规划约束：standalone_query 已经是语义完整 query；默认原样使用，不要二次扩写。",
        ]
    )


def format_reflect_user(
    question: str,
    standalone_query: str,
    executed_queries: list[str],
    evidence_text: str,
) -> str:
    return "\n\n".join(
        [
            f"原始问题：{question}",
            f"独立问题：{standalone_query}",
            "已执行检索：\n" + "\n".join(f"- {q}" for q in executed_queries),
            "当前证据：\n" + (evidence_text or "无"),
        ]
    )


def format_answer_user(
    question: str,
    standalone_query: str,
    route: str,
    model_name: str,
    evidence_assessment: dict[str, Any],
    evidence_text: str,
    selected_tool: str | None = None,
    tool_input: dict[str, Any] | None = None,
    tool_result: dict[str, Any] | None = None,
    current_tool_context: dict[str, Any] | None = None,
    execution_plan: dict[str, Any] | None = None,
    task_results: list[dict[str, Any]] | None = None,
    completion_assessment: dict[str, Any] | None = None,
) -> str:
    compact_assessment = compact_evidence_assessment(evidence_assessment)
    return "\n\n".join(
        [
            f"原始问题：{question}",
            f"独立问题：{standalone_query}",
            f"route：{route}",
            f"当前项目配置的聊天模型：{model_name}",
            "execution_plan：\n" + json.dumps(execution_plan or {}, ensure_ascii=False, indent=2),
            "task_results：\n" + json.dumps(task_results or [], ensure_ascii=False, indent=2),
            "completion_assessment：\n" + json.dumps(completion_assessment or {}, ensure_ascii=False, indent=2),
            f"selected_tool：{selected_tool or '无'}",
            "tool_input：\n" + json.dumps(tool_input or {}, ensure_ascii=False, indent=2),
            "tool_result：\n" + json.dumps(tool_result or {}, ensure_ascii=False, indent=2),
            "current_tool_context：\n" + json.dumps(current_tool_context or {}, ensure_ascii=False, indent=2),
            f"证据评估：{compact_assessment or '无'}",
            "证据：\n" + (evidence_text or "无"),
        ]
    )


def format_completion_reflect_user(
    question: str,
    execution_plan: dict[str, Any],
    task_results: list[dict[str, Any]],
    evidence_text: str,
    sources: list[dict[str, Any]],
    completion_round: int,
) -> str:
    compact_sources = [
        {
            "source": item.get("source"),
            "title_path": item.get("title_path"),
            "chunk_id": item.get("chunk_id"),
        }
        for item in sources[:8]
    ]
    return "\n\n".join(
        [
            f"原始问题：{question}",
            f"completion_round：{completion_round}",
            "execution_plan：\n" + json.dumps(execution_plan or {}, ensure_ascii=False, indent=2),
            "task_results：\n" + json.dumps(task_results or [], ensure_ascii=False, indent=2),
            "当前证据摘要：\n" + (evidence_text or "无"),
            "sources：\n" + json.dumps(compact_sources, ensure_ascii=False, indent=2),
        ]
    )


def compact_evidence_assessment(evidence_assessment: dict[str, Any] | None) -> dict[str, Any]:
    if not evidence_assessment:
        return {}
    output: dict[str, Any] = {}
    for key in ("is_sufficient", "can_answer_partial", "should_continue_retrieval"):
        if key in evidence_assessment:
            output[key] = evidence_assessment.get(key)
    missing = evidence_assessment.get("missing_information") or []
    if isinstance(missing, list) and missing:
        output["missing_information"] = [str(item) for item in missing[:5]]
    stop_reason = str(evidence_assessment.get("stop_reason") or "").strip()
    if stop_reason:
        output["stop_reason"] = truncate(stop_reason, 120)
    return output


def format_memory_user(question: str, standalone_query: str, answer: str, old_summary: str) -> str:
    clean_answer = strip_citations_and_metadata(answer)
    return "\n\n".join(
        [
            f"旧摘要：{old_summary or '无'}",
            f"用户问题：{question}",
            f"独立问题：{standalone_query}",
            f"助手回答：{clean_answer}",
        ]
    )
