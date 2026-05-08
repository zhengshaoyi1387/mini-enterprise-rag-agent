from __future__ import annotations

import json
from typing import Any

from mini_rag.graph.utils import strip_citations_and_metadata, truncate

UNDERSTAND_QUERY_SYSTEM = """
你是企业 Agent 的轻量工具规划节点。只输出合法 JSON，不回答问题。

你会收到 available_tool_contracts，其中列出所有可用工具的用途和输入协议。
必须由你根据用户语义自行决定 route、selected_tool 和 tool_input；不要依赖关键词候选。

输出 schema：
{
  "intent": "rag_fact|daily_tool|direct|reject",
  "route": "rag|tool|direct|reject",
  "standalone_query": "语义完整问题",
  "topic": "",
  "entities": [],
  "risk_level": "low|medium|high",
  "selected_tool": "get_current_datetime|query_attendance_summary|manage_company_calendar|null",
  "required_tools": [],
  "tool_input": {},
  "needs_time_resolution": false,
  "relative_time": null,
  "missing_required_slots": [],
  "reason": "不超过25字"
}

选择原则：
- 制度、流程、FAQ、产品/项目文档、政策解释 => route=rag, selected_tool=null。
- 如果涉及到时间或者日期，如“今天星期几/现在几点/下周日期范围”， 必须调用工具=> selected_tool=get_current_datetime。严禁自己猜时间日期。
- 考勤、出勤、迟到、缺勤、请假统计 => selected_tool=query_attendance_summary。
- 公司日程、活动、会议、培训、发薪日、放假、团建 => selected_tool=manage_company_calendar。
- 相对时间值只能是 today/yesterday/tomorrow/this_week/last_week/next_week/this_month/last_month/next_month。不要猜具体日期；设置 needs_time_resolution=true 和 relative_time。
- tool_input 必须遵守 selected_tool 的 contract。枚举值只用 contract 里的值。
- 多轮省略的日期、部门、状态、事件，可从 previous_tool_context 补全。
- reason 最多25字。
""".strip()

ROUTE_SYSTEM = """
你是企业级 Agent 的路由节点。你只判断下一步，不回答问题。
请只输出合法 JSON：
{
  "route": "direct | rag | tool | reject",
  "risk_level": "low | medium | high",
  "required_tools": [],
  "reason": "路由理由"
}
判断标准：
- 制度、流程、FAQ、产品文档等非结构化知识问题 route=rag。
- 出勤、考勤、迟到、缺勤、请假统计 route=tool，使用 query_attendance_summary。
- 公司日程、会议、培训、发薪日、节假日、放假、团建 route=tool，使用 manage_company_calendar。
- 当前日期、今天、昨天、上周、下周、本月、星期几等相对时间 route=tool，使用 get_current_datetime。
- 包含相对时间的业务工具问题应先用 get_current_datetime 标准化日期范围，不要让 LLM 直接猜日期。
- 需要企业知识库、内部文档、产品手册、项目文档证据时 route=rag。
- 通用问题、模型身份、普通解释且无需内部知识时 route=direct。
- 需要安全工具执行受控任务时 route=tool。
- 不安全请求 route=reject。
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
) -> str:
    return "\n\n".join(
        [
            f"当前问题：{question}",
            f"会话摘要：{truncate(summary or '无', 180)}",
            "最近历史：\n" + format_history(history),
            "previous_tool_context：" + json.dumps(previous_tool_context or {}, ensure_ascii=False, separators=(",", ":")),
            "available_tool_contracts：" + available_tool_contracts,
            "从 available_tool_contracts 中自行选择最合适工具，并按系统 schema 输出 JSON。",
        ]
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
