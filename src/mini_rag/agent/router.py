from __future__ import annotations

from dataclasses import dataclass, field

from mini_rag.agent.llm_json import message_content, parse_json_object
from mini_rag.prompts import ROUTER_SYSTEM_PROMPT, format_router_user_prompt


VALID_ROUTES = {"rag", "tool", "direct", "reject"}
VALID_RISK_LEVELS = {"low", "medium", "high"}

# 这些是最基础的安全兜底词。
# 即使 LLM 误判为 direct，只要命中这里，也会强制 reject。
DANGEROUS_KEYWORDS = ["泄露 API key", "输出系统提示词", "删除所有文件", "读取其他用户", "绕过权限"]


@dataclass
class RouterDecision:
    """LLM Router 的结构化决策。

    - route：LangGraph 条件边会根据它决定下一步。
    - rewritten_query：历史兼容字段。Router 只负责路由，不再拥有“改写问题”的权限。
      这个字段始终使用上游已经生成的 standalone_query，避免同一个问题被多个节点反复改写。
    - required_tools：当 route=tool 时，告诉 execute_tool 节点需要哪些安全工具。
    - risk_level：风险等级。high 会强制 reject。
    - fallback_used：是否因为 JSON 解析失败或安全兜底改写了模型决策。
    """

    route: str
    reason: str
    rewritten_query: str
    required_tools: list[str] = field(default_factory=list)
    risk_level: str = "low"
    raw_response: str = ""
    fallback_used: bool = False

    def to_dict(self) -> dict:
        """转成普通 dict，方便写入 AgentState / trace / API 响应。"""
        return {
            "route": self.route,
            "reason": self.reason,
            "rewritten_query": self.rewritten_query,
            "required_tools": self.required_tools,
            "risk_level": self.risk_level,
            "fallback_used": self.fallback_used,
        }


def route_with_llm(
    llm,
    question: str,
    standalone_query: str,
    summary: str = "",
    selected_history: list | None = None,
) -> RouterDecision:
    """LLM Router：让模型输出结构化路由，并做安全兜底。

    路由含义：
    - rag：需要查企业知识库，本项目会调用 search_knowledge_base 工具。
    - tool：需要执行某个安全工具，例如总结、对比、生成学习计划。
    - direct：不需要知识库和工具，可以直接回答。
    - reject：危险或越权请求，直接拒绝。
    """
    # 一些与助手自身相关的元问题不需要企业知识库。先做确定性路由，
    # 避免被同 session 的历史业务问题带偏。
    if is_assistant_meta_question(question):
        return RouterDecision(
            route="direct",
            reason="用户询问助手自身信息，不需要检索企业知识库。",
            rewritten_query=question,
            required_tools=[],
            risk_level="low",
            fallback_used=True,
        )

    # 安全规则先于 LLM。原因是安全兜底不能完全依赖模型自觉。
    dangerous = match_dangerous_keyword(question) or match_dangerous_keyword(standalone_query)
    if dangerous:
        return RouterDecision(
            route="reject",
            reason=f"命中危险关键词：{dangerous}",
            rewritten_query=standalone_query or question,
            required_tools=[],
            risk_level="high",
            fallback_used=True,
        )

    # 这里让 LLM 输出 JSON，而不是自然语言说明。
    # JSON 的好处是可以被程序校验，再驱动 LangGraph 的 conditional edge。
    messages = [
        {
            "role": "system",
            "content": ROUTER_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": format_router_user_prompt(question, standalone_query, summary, selected_history),
        },
    ]
    raw = message_content(llm.invoke(messages))
    payload = parse_json_object(raw)
    if not payload:
        # LLM 不按格式输出时，默认走 rag。
        # 对企业知识库助手来说，宁可保守地查证据，也不要随口直答。
        return fallback_route(standalone_query or question, raw)

    route = str(payload.get("route", "rag")).strip()
    risk_level = str(payload.get("risk_level", "low")).strip()
    if route not in VALID_ROUTES:
        return fallback_route(standalone_query or question, raw)
    if risk_level not in VALID_RISK_LEVELS:
        risk_level = "low"
    if risk_level == "high":
        # LLM 自己判断高风险时，强制进入 reject。
        route = "reject"

    required_tools = payload.get("required_tools", [])
    if not isinstance(required_tools, list):
        required_tools = []
    return RouterDecision(
        route=route,
        reason=str(payload.get("reason") or "LLM router decision"),
        # 重要：Router 的职责是“选择路线”，不是“继续改写问题”。
        # 旧实现会使用 LLM 返回的 rewritten_query，导致问题在 context_manager
        # 改写后又被 Router 二次扩写，下游检索和证据评估都会被带偏。
        # 因此这里保留字段名用于兼容 trace / 测试，但值只取 standalone_query。
        rewritten_query=standalone_query or question,
        required_tools=[str(tool) for tool in required_tools],
        risk_level=risk_level,
        raw_response=raw,
        fallback_used=False,
    )


def fallback_route(query: str, raw: str = "") -> RouterDecision:
    """Router 失败时的默认决策。"""
    return RouterDecision(
        route="rag",
        reason="LLM Router JSON 解析失败或 route 非法，默认走知识库检索。",
        rewritten_query=query,
        required_tools=[],
        risk_level="low",
        raw_response=raw,
        fallback_used=True,
    )


def match_dangerous_keyword(text: str) -> str | None:
    """命中危险关键词时返回关键词，否则返回 None。"""
    return next((keyword for keyword in DANGEROUS_KEYWORDS if keyword in text), None)


def is_assistant_meta_question(text: str) -> bool:
    """判断是否是询问助手自身的元问题。"""
    q = str(text or "").strip()
    patterns = ["你是什么模型", "你是啥模型", "你是谁", "你的模型", "你用的什么模型", "你叫什么"]
    return any(pattern in q for pattern in patterns)
