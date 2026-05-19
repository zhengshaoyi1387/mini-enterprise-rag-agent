from __future__ import annotations

import json
from typing import Any

from mini_rag.answer.packet import compact_task_results
from mini_rag.graph.utils import strip_citations_and_metadata, truncate


PLAN_WITH_LLM_SYSTEM = """
你是企业 Agent 的唯一 Planner。只输出 JSON，不回答用户。

你负责理解用户意图、拆分任务、选择工具或 RAG，但不要计算具体日期。
时间字段必须保留用户原始表达，写入 time_expression，例如“今天”“明天”“后天”“下周三”“今天、明天、下周一”“本周”“下月”。
不要输出任何程序枚举型相对日期；不要输出 YYYY-MM-DD，除非用户原文直接给出了绝对日期。

输出 schema：
{
  "overall_intent": "datetime | calendar | attendance | rag | mixed | smalltalk",
  "requires_tools": true,
  "requires_rag": false,
  "tasks": [
    {
      "task_id": "t1",
      "kind": "tool | rag | answer",
      "objective": "子目标",
      "tool_name": "manage_company_calendar | query_attendance_summary | get_current_datetime | null",
      "action": "query | create | update | delete | * | null",
      "time_expression": "用户原始时间表达或 null",
      "tool_input": {},
      "rag_query": null,
      "depends_on": []
    }
  ],
  "answer_style": "concise | detailed"
}

规则：
- 时间类问题可用 kind=answer，并填写 time_expression；程序会解析日期和星期。
- 日历/考勤用 kind=tool；工具入参只填业务槽位，不填由相对时间换算出的 date/start_date/end_date。
- update/delete 若没有具体 event_id，先规划 query，再规划 write task，并用 selector 表示目标范围；不要伪造 all/multiple/from_x 这类 event_id。
- 考勤异常代表 late + leave + absent；明细/记录/谁/名单时 include_records=true 且 group_by=employee。
- 企业制度/政策/说明走 kind=rag；mixed 请求必须同时保留 tool 和 rag 两类任务。
- 不要新增用户没问的任务。

只输出 JSON。
""".strip()


REACT_NEXT_ACTION_SYSTEM = """
你是受控 ReAct 执行器的下一步动作选择器。只输出 JSON，不回答用户。

你只能在 approved execution_plan 范围内选择下一步，不能新增任务，不能绕过权限、日期解析、工具 schema 或写安全门禁。
所有日期只能使用 resolved_time_facts 和已解析 task.tool_input，不要重新计算日期。
如果剩余任务为空或已有 observations 足够覆盖目标，输出 finish。

输出 schema：
{
  "thought": "一句话说明为什么执行这一步",
  "next_action": "call_tool | search_rag | finish | ask_clarification",
  "task_id": "t1",
  "tool_name": "工具名或 null",
  "tool_input": {},
  "rag_query": "检索 query 或 null",
  "finish_reason": "结束或澄清原因"
}
""".strip()


GENERATE_ANSWER_SYSTEM = """
你是严谨的企业知识库 Agent。最终回答只能基于 AnswerPacket 中的结构化事实。

硬规则：
- 日期和星期只能来自 resolved_time_facts 或 tool_results；不要自行推算。
- 不要编造会议、考勤、工具结果、权限结果或 RAG 引用。
- RAG 引用只能使用 packet 中实际 retrieved evidence 的 source/title_path/chunk_id。
- evidence 不足时明确说当前可访问知识库没有找到明确依据。
- 权限/安全/澄清事件是 locked facts，只能解释原因，不能改写成允许执行。
- tool answer 不要添加 RAG 引用；RAG answer 不要伪造 tool 结果。
- 日历/考勤结果使用工具返回的日期、星期、时间、标题、地点、员工/部门等字段。

使用自然、简洁、结构清晰的中文回答。
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
不要保存 source/title_path/chunk_id/vector_score 等引用或 trace 字段。
""".strip()


def format_plan_with_llm_user(
    question: str,
    role: str | None = None,
    planning_context: dict[str, Any] | None = None,
    capability_catalog: str = "[]",
    permissions: dict[str, Any] | None = None,
    time_context: dict[str, Any] | None = None,
) -> str:
    compact_time = {
        key: (time_context or {}).get(key)
        for key in ("current_date", "current_time", "weekday_zh", "timezone")
        if (time_context or {}).get(key) not in (None, "", [], {})
    }
    return "\n".join(
        [
            f"role={role or 'unknown'}",
            "permissions=" + json.dumps(permissions or {}, ensure_ascii=False, separators=(",", ":"), default=str),
            "capability_catalog=" + capability_catalog,
            "planning_context=" + json.dumps(planning_context or {}, ensure_ascii=False, separators=(",", ":"), default=str),
            "time_context_for_reference_only=" + json.dumps(compact_time, ensure_ascii=False, separators=(",", ":"), default=str),
            f"current_message={question}",
        ]
    )


def format_react_next_action_user(
    question: str,
    plan: dict[str, Any],
    remaining_tasks: list[dict[str, Any]],
    completed_tasks: list[str],
    observations: list[dict[str, Any]],
    resolved_time_facts: list[dict[str, Any]],
) -> str:
    compact_observations = []
    for item in observations[-8:]:
        if not isinstance(item, dict):
            continue
        compact_observations.append(
            {
                key: item.get(key)
                for key in ("step", "task_id", "action", "status", "summary", "type")
                if item.get(key) not in (None, "", [], {})
            }
        )
    return "\n\n".join(
        [
            f"question={question}",
            "execution_plan=" + json.dumps(plan or {}, ensure_ascii=False, indent=2, default=str),
            "remaining_tasks=" + json.dumps(remaining_tasks or [], ensure_ascii=False, indent=2, default=str),
            "completed_tasks=" + json.dumps(completed_tasks or [], ensure_ascii=False, separators=(",", ":"), default=str),
            "resolved_time_facts=" + json.dumps(resolved_time_facts or [], ensure_ascii=False, indent=2, default=str),
            "observations=" + json.dumps(compact_observations, ensure_ascii=False, indent=2, default=str),
        ]
    )


def compact_evidence_assessment(evidence_assessment: dict[str, Any] | None) -> dict[str, Any]:
    if not evidence_assessment:
        return {}
    output: dict[str, Any] = {}
    for key in ("answerable", "is_sufficient", "can_answer_partial", "should_continue_retrieval"):
        if key in evidence_assessment:
            output[key] = evidence_assessment.get(key)
    message = str(evidence_assessment.get("message") or evidence_assessment.get("reason") or "").strip()
    if message:
        output["message"] = truncate(message, 180)
    return output


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
    role_allowed_actions: dict[str, list[str]] | None = None,
) -> str:
    del selected_tool, tool_input, tool_result, current_tool_context, model_name
    main_question = question.strip() or standalone_query.strip()
    raw_task_results = [item for item in (task_results or []) if isinstance(item, dict)]
    if raw_task_results and all("类型" in item or "证据" in item or "时间事实" in item for item in raw_task_results):
        completed_tasks = raw_task_results
    else:
        completed_tasks = compact_task_results(raw_task_results, datetime_context=f"{question}\n{standalone_query}".lower())

    lines = [
        f"用户原始问题：{main_question}",
        f"route：{str(route or 'direct').lower()}",
        "AnswerPacket：",
        json.dumps(
            {
                "question": main_question,
                "standalone_query": standalone_query,
                "resolved_and_task_facts": completed_tasks,
                "rag_evidence_text": evidence_text or "",
                "evidence_assessment": compact_evidence_assessment(evidence_assessment),
                "completion_assessment": completion_assessment or {},
                "role_allowed_actions": role_allowed_actions or {},
                "execution_plan": execution_plan or {},
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    ]
    return "\n\n".join(lines)


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
