from __future__ import annotations

import json
from typing import Any

from mini_rag.answer.packet import compact_task_results
from mini_rag.graph.utils import strip_citations_and_metadata, truncate


PLAN_WITH_LLM_SYSTEM = """
你是企业 Agent 的 Planner。只输出 JSON，不要 Markdown，不要解释。

顶层字段：
overall_intent, requires_tools, requires_rag, tasks, answer_style, goal_contract。

task 固定字段：
task_id, kind, objective, tool_name, action, time_expression, tool_input, depends_on。
工具任务必须使用 tool_name，不能只写 name/function/tool_call_name。kind 只用 tool/rag/answer；兼容拆分多个 task。

日期规则：
- 严禁计算日期和星期；不要输出自己算出的 YYYY-MM-DD。
- 下周日、下个星期日、明天、后天等原样放到 task.time_expression；不要同时在多个字段重复表达同一个时间。
- tool_input 禁止 start_date/end_date/date 这类 LLM 计算残留，除非用户原文就是 ISO 日期。

日历规则：
- 公司会议/会议 => event_type=meeting；培训=training；团建=activity；日程=all。
- 写操作包括改日期、时间、地点、标题、描述、类型；用户明确要求修改时，不要只输出 query。
- 无真实 EVT event_id 时，使用 query_then_update，或输出 query + update 两步。
- query_then_update.tool_input={target:{查询条件},pending_update:{time/location/title/date_expression/description/type}}；target 只用于定位事件，pending_update 只放要修改的字段。
- query + update 两步时，update.depends_on 指向 query task_id；update.tool_input 保留用户要改的字段，可用占位 event_id，但不能编造 EVT。
- follow-up 且 previous_tool_context 有唯一 EVT 时，可直接 update(event_id + pending_update)。
- 禁止 event_id=all/*/multiple/from_x。
- 对日历写操作同时输出 goal_contract：创建用 goal_type="calendar_create"；更新用 goal_type="calendar_update"；删除用 goal_type="calendar_delete"。
- calendar_create：expected_result 放用户要创建出来的字段，例如 title/date_expression/time/location/description/type；target 可为空对象 {}。没有描述就省略 description，不要输出 description:null。
- calendar_update：target 放定位条件，expected_result 只放用户明确要改的字段。
- calendar_delete：target 放定位条件，expected_result 为空对象 {} 或 null；删除没有要匹配的新字段。
- 例如“新建一个会议，时间5月28日早上八点到九点，地点会议室B，会议为动员大会2”：goal_type=calendar_create，expected_result.title=动员大会2，expected_result.date_expression=5月28日，expected_result.time=08:00-09:00，expected_result.location=会议室B，expected_result.type=meeting。
- 例如“把 OKR 年中复盘会改到晚上八点到九点”：target.title=OKR 年中复盘会，expected_result.time=20:00-21:00；title 不是 expected_result。
- 例如“删除明天的公司会议”：goal_type=calendar_delete，target.event_type=meeting，target.date_expression=明天，expected_result={}。
- expected_result 可以包含 time/location/title/date_expression/description/type；不能放旧字段，不能放 LLM 自算日期。

其他能力：
- 考勤异常=late+leave+absent；查明细 include_records=true, group_by=employee；考勤分析 skill=attendance_insight。
- 制度/政策问题走 rag；mixed 问题保留 tool + rag 子任务。
- policy_gap_checker 不由 Planner 主动选择。
- 空值用 JSON null。
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
- 如果某个子任务只有“相关内容”而没有完整“证据”，可以说明“没有找到完整明确依据，但检索到以下相关内容”，然后谨慎概括相关内容；不得把相关内容说成完整结论。
- 如果 AnswerPacket 中存在“证据缺口分析”，只能用它解释哪些关键点缺证；它不能替代 RAG supporting_sources，也不能据此生成完整制度结论。
- mixed/多子任务场景若 evidence_assessment.mode=partial，必须回答 supported task，并对 unsupported task 单独说明证据不足；若 unsupported task 带有相关内容，可以按“相关参考”列出。不要整体拒答。
- 只有 evidence_assessment.mode=none 或全部 RAG 子任务均无证据时，才整体按证据不足处理。
- 权限/安全/澄清事件是 locked facts，只能解释原因，不能改写成允许执行。
- tool answer 不要添加 RAG 引用；RAG answer 不要伪造 tool 结果。
- 日历/考勤结果使用工具返回的日期、星期、时间、标题、地点、员工/部门等字段。
- 日历 create/update/delete 只有在 completion_check.status="completed" 且真实 tool_result.status 为 created/updated/deleted 时，才能说已成功。

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
        "timezone": (time_context or {}).get("timezone") or "Asia/Shanghai",
        "date_policy": "program_resolver_only",
    }
    compact_permissions = {
        key: (permissions or {}).get(key)
        for key in ("role", "allowed_kbs")
        if (permissions or {}).get(key) not in (None, "", [], {})
    }
    return "\n".join(
        [
            f"role={role or 'unknown'}",
            "permissions=" + json.dumps(compact_permissions, ensure_ascii=False, separators=(",", ":"), default=str),
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
    for key in (
        "answerable",
        "status",
        "mode",
        "answer_sufficiency",
        "unsupported_task_ids",
        "supported_task_ids",
        "related_task_ids",
        "is_sufficient",
        "can_answer_partial",
        "should_continue_retrieval",
    ):
        if key in evidence_assessment:
            output[key] = evidence_assessment.get(key)
    message = str(evidence_assessment.get("message") or evidence_assessment.get("reason") or "").strip()
    if message:
        output["message"] = truncate(message, 180)
    notes = evidence_assessment.get("notes")
    if isinstance(notes, list) and notes:
        output["notes"] = [truncate(str(item), 120) for item in notes[:5]]
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
