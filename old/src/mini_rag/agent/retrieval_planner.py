from __future__ import annotations

from dataclasses import dataclass

from mini_rag.agent.llm_json import message_content, parse_json_object
from mini_rag.prompts import RETRIEVAL_PLANNER_SYSTEM_PROMPT, format_retrieval_planner_user_prompt


@dataclass
class RetrievalPlan:
    """检索规划器的结构化输出。

    search_queries 是 execute_tool 真正会逐条检索的问题列表。
    对多模块问题来说，这里应该从一个大问题拆成多个更窄的 query。
    """

    search_queries: list[str]
    reason: str
    raw_response: str = ""
    fallback_used: bool = False

    def to_dict(self) -> dict:
        return {
            "search_queries": self.search_queries,
            "reason": self.reason,
            "fallback_used": self.fallback_used,
        }


def plan_retrieval(
    llm,
    question: str,
    standalone_query: str,
    router_decision: dict,
) -> RetrievalPlan:
    """让 LLM 规划检索 query。

    这里不靠代码规则硬切“、”，而是让 LLM 判断是否需要拆分。
    但 LLM 输出必须是 JSON，并且程序会做去重、限长、fallback。
    """
    messages = [
        {"role": "system", "content": RETRIEVAL_PLANNER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": format_retrieval_planner_user_prompt(question, standalone_query, router_decision),
        },
    ]
    raw = message_content(llm.invoke(messages))
    payload = parse_json_object(raw)
    if not payload:
        return fallback_retrieval_plan(standalone_query or question, raw)

    queries = normalize_queries(payload.get("search_queries"), fallback=standalone_query or question)
    return RetrievalPlan(
        search_queries=queries,
        reason=str(payload.get("reason") or "LLM retrieval planner"),
        raw_response=raw,
        fallback_used=False,
    )


def fallback_retrieval_plan(query: str, raw: str = "") -> RetrievalPlan:
    """检索规划失败时退回单 query 检索。"""
    return RetrievalPlan(
        search_queries=[query],
        reason="检索规划 JSON 解析失败，退回单 query 检索。",
        raw_response=raw,
        fallback_used=True,
    )


def normalize_queries(value, fallback: str, max_queries: int = 5) -> list[str]:
    """清洗 LLM 输出的 query 列表。

    新手注意：即使 prompt 要求 array[string]，真实 LLM 也可能输出空数组、数字、
    重复项或者很长的列表。这里统一兜住，避免下游工具拿到脏数据。
    """
    if not isinstance(value, list):
        return [fallback]

    queries: list[str] = []
    for item in value:
        query = str(item).strip()
        if query and query not in queries:
            queries.append(query)
        if len(queries) >= max_queries:
            break
    return queries or [fallback]
