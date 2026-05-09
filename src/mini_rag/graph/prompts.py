from __future__ import annotations

import json
from typing import Any

from mini_rag.graph.utils import strip_citations_and_metadata, truncate

UNDERSTAND_QUERY_SYSTEM = """
你是企业 Agent 的结构化 Planner。只输出合法 JSON，不回答问题。
你必须先理解“当前消息本身”，再决定是否使用历史或 previous_tool_context。
你会收到 available_tool_contracts，其中只列出当前角色允许使用的工具和 action。
你只能选择 available_tool_contracts 中存在的工具和 action；如果能力不可见，必须输出 permission_required direct。

输出 schema：
{
  "message_type": "smalltalk|business_question|followup_question|command|unsafe",
  "context_usage": "none|use_history|use_previous_tool_context",
  "intent": "smalltalk|rag_fact|daily_tool|permission_required|direct|reject",
  "route": "direct|rag|tool|reject",
  "standalone_query": "语义完整问题",
  "topic": "",
  "entities": [],
  "risk_level": "low|medium|high",
  "selected_tool": "string|null",
  "selected_action": "string|null",
  "required_tools": [],
  "tool_input": {},
  "needs_time_resolution": false,
  "relative_time": null,
  "missing_required_slots": [],
  "reason": "不超过25字"
}

选择原则：
- 当前消息优先。不要被历史上下文过度牵引。
- smalltalk 例如“你好/在吗/谢谢/好的/再见”：message_type=smalltalk, context_usage=none, intent=smalltalk, route=direct, selected_tool=null, selected_action=null, tool_input={}，禁止使用 previous_tool_context。
- followup_question 例如“谁迟到了/还有别的吗/具体是哪几个/那下周呢”：只有当前问题明显依赖上一轮业务内容时，才允许 context_usage=use_history 或 use_previous_tool_context。
- 制度、流程、FAQ、产品/项目文档、政策解释 => route=rag, selected_tool=null, selected_action=null。
- 纯日期时间问题，如“今天星期几/现在几点/下周日期范围”必须调用工具 => selected_tool=get_current_datetime, selected_action="*"。严禁猜具体日期。
- 考勤、出勤、迟到、缺勤、请假统计 => selected_tool=query_attendance_summary, selected_action="*"。
- 公司日程、会议、培训、发薪日、放假、团建 => selected_tool=manage_company_calendar，并按可见 actions 选择 query/create/update/delete。
- 如果用户请求的工具或 action 不在 available_tool_contracts 中：intent=permission_required, route=direct, selected_tool=null, selected_action=null, tool_input={}。
- 相对时间值只能是 today/yesterday/tomorrow/this_week/last_week/next_week/this_month/last_month/next_month。不要猜具体日期；设置 needs_time_resolution=true 和 relative_time。
- 业务数据问题中 get_current_datetime 只是内部时间解析依赖，不是最终 selected_tool；日程问题最终选择 manage_company_calendar，考勤问题最终选择 query_attendance_summary。
- tool_input 必须遵守 selected_tool 的 contract。枚举值只用 contract 里的值。
- reason 最多30个中文字符。
""".strip()

TIME_REFERENCE_SYSTEM = """
你是企业 Agent 的时间引用归一化器。只输出合法 JSON，不回答问题。
你只判断“当前用户消息本身”是否包含需要用当前日期时间解析的时间引用；不要从历史或 previous_tool_context 继承日期。

输出 schema：
{
  "has_time_reference": false,
  "needs_time_resolution": false,
  "relative_time": null,
  "is_datetime_only": false,
  "reason": "不超过20字"
}

约束：
- relative_time 只能是 null 或以下规范值之一：today/yesterday/tomorrow/this_week/last_week/next_week/this_month/last_month/next_month。
- 不输出具体日期，不猜测日期范围；具体日期只能由 get_current_datetime 工具结果产生。
- 如果当前消息只是询问日期、时间、星期、日期范围，is_datetime_only=true。
- 如果当前消息是业务问题但带时间引用，is_datetime_only=false；业务工具仍是最终工具，get_current_datetime 只是内部依赖。
- 如果当前消息没有时间引用，has_time_reference=false, needs_time_resolution=false, relative_time=null。
""".strip()

PLAN_RETRIEVAL_SYSTEM = """
你是 Agentic RAG 的检索规划节点。注意：上一步 understand_query 已经产出语义完整的 standalone_query。
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
- 禁止把 standalone_query 再扩写成更宽泛的问题；禁止添加用户没有要求的“原理、优势、案例、流程、风险、最佳实践”等维度。
- 只有用户明确比较多个对象，或 standalone_query 里确实包含多个对象且需要分别找证据时，才允许拆成最多 3 个任务。
- 拆分时每个 query 仍必须围绕 standalone_query，不得创造新问题；可以加明确对象名，但不要扩大范围。
- 如果只是问“有哪些/包含哪些/规则是什么”，优先用 standalone_query 一次整体检索。
- 检索任务越少越好，目的是提高召回精度和降低延迟。
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
- 如果用户只问“有哪些/包含哪些”，有完整列表证据即可充分，不要要求每个对象的详细功能。
- 如果用户要求介绍/解释多个对象，每个对象应有相应证据；缺失时可 partial。
- 只有当补检索很可能带来新的、可回答用户问题的证据时，should_continue_retrieval 才设为 true。
- followup_tasks 只补当前问题最关键的缺失信息，不要重复已经检索过的 query。
- 如果已有证据可部分回答，且继续检索大概率只是重复命中概述，should_continue_retrieval=false，直接部分回答。
""".strip()

GENERATE_ANSWER_SYSTEM = """
你是严谨的企业知识库 Agent。请基于输入中的证据、工具结果和证据评估回答用户。
你不负责重新检索，不负责扩大问题范围，只负责基于已给证据或工具结果生成答案。
要求：
- 回答当前用户问题，不要复读历史无关内容。
- 使用自然、简洁、结构清晰的中文。
- 证据不足时说明不足，但不要输出 debug 风格的 chunk 罗列。
- 没有证据支持的对象，只说明“当前资料未提供详细说明”，不要根据常识推测功能。
- 如果是 direct 问题，可直接回答；如果涉及当前模型配置，请使用输入中给出的模型配置。
- RAG 答案末尾列出引用来源，包含 source、title_path、chunk_id。
- 工具答案不要直接输出原始 JSON，要把 tool_result 转成自然语言；权限或参数错误要用用户能理解的话解释。
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


def format_history(history: list[dict[str, Any]], max_chars: int = 520) -> str:
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
                    f"助手记忆：{truncate(answer, 160)}",
                ]
            )
        )
    return truncate("\n\n".join(lines), max_chars)


def format_understand_user(
    question: str,
    summary: str,
    history: list[dict[str, Any]],
    candidate_tool: str | None = None,
    previous_tool_context: dict[str, Any] | None = None,
    available_tool_contracts: str = "[]",
    role: str | None = None,
) -> str:
    _ = candidate_tool
    return "\n\n".join(
        [
            f"当前问题：{question}",
            f"当前角色：{role or 'unknown'}",
            f"会话摘要：{truncate(summary or '无', 180)}",
            "最近历史：\n" + format_history(history),
            "previous_tool_context：" + json.dumps(previous_tool_context or {}, ensure_ascii=False, separators=(",", ":")),
            "available_tool_contracts：" + available_tool_contracts,
            "只能从 available_tool_contracts 中选择工具和 action；如果能力不可见，输出 permission_required direct。",
        ]
    )


def format_time_reference_user(
    question: str,
    standalone_query: str,
    planner_context: dict[str, Any] | None = None,
) -> str:
    return "\n\n".join(
        [
            f"当前用户消息：{question}",
            f"planner_standalone_query：{standalone_query}",
            "planner_context：" + json.dumps(planner_context or {}, ensure_ascii=False, separators=(",", ":")),
            "只判断当前用户消息本身的时间引用；不要从 planner_context 或历史继承日期。",
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
) -> str:
    compact_assessment = compact_evidence_assessment(evidence_assessment)
    return "\n\n".join(
        [
            f"原始问题：{question}",
            f"独立问题：{standalone_query}",
            f"route：{route}",
            f"当前项目配置的聊天模型：{model_name}",
            f"selected_tool：{selected_tool or '无'}",
            "tool_input：\n" + json.dumps(tool_input or {}, ensure_ascii=False, indent=2),
            "tool_result：\n" + json.dumps(tool_result or {}, ensure_ascii=False, indent=2),
            "current_tool_context：\n" + json.dumps(current_tool_context or {}, ensure_ascii=False, indent=2),
            f"证据评估：{compact_assessment or '无'}",
            "证据：\n" + (evidence_text or "无"),
        ]
    )


def compact_evidence_assessment(evidence_assessment: dict[str, Any] | None) -> dict[str, Any]:
    """只把最终回答需要的证据评估字段交给 LLM。"""
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
