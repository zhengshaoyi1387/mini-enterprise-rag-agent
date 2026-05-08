from __future__ import annotations

from langchain.agents import create_agent

from mini_rag.agent.session import InMemorySessionStore, default_session_store
from mini_rag.agent.tools import (
    create_compare_sources_tool,
    create_rewrite_query_tool,
    create_search_knowledge_base_tool,
    create_summarize_sources_tool,
)
from mini_rag.config import Settings
from mini_rag.models.qwen import build_qwen_chat_model
from mini_rag.observability.timer import Timer
from mini_rag.rag.prompt import AGENT_SYSTEM_PROMPT
from mini_rag.retrieval.retriever import KnowledgeBaseRetriever


class LegacyEnterpriseKnowledgeAgent:
    """旧版 create_agent Agent，用于和 LangGraph 状态机对比。

    它保留了之前的“脚本式 Agent”写法：
    一次性创建工具列表 -> create_agent -> invoke。

    对新手来说，可以把它和 graph_agent.py 对比着看：
    - legacy_agent.py：流程隐式藏在 LangChain agent 内部。
    - graph_agent.py：流程显式拆成节点和边。
    """

    def __init__(self, settings: Settings, session_store: InMemorySessionStore | None = None):
        self.settings = settings
        self.llm = build_qwen_chat_model(settings)
        self.retriever = KnowledgeBaseRetriever(settings)
        default_session_store.max_turns = settings.session_max_turns
        self.session_store = session_store or default_session_store

    def ask(
        self,
        question: str,
        session_id: str | None = None,
        retrieval_mode: str | None = None,
        enable_rerank: bool | None = None,
        user_id: str | None = None,
        role: str | None = None,
        trace_id: str | None = None,
        kb_ids: list[str] | None = None,
    ) -> dict:
        history = self.session_store.get_history(session_id)
        # legacy 路径仍然使用旧的 InMemorySessionStore。
        # 它只是保留用于对比；默认生产/演示路径已经切到 SQLite + LangGraph。
        trace: dict = {
            "mode": "legacy_create_agent",
            "trace_id": trace_id,
            "user_id": user_id,
            "role": role,
            "question": question,
            "session_id": session_id,
            "history_turn_count": len(history),
            "retrieval_mode": retrieval_mode or self.settings.retrieval_mode,
            "enable_rerank": self.settings.rerank_enabled if enable_rerank is None else enable_rerank,
        }

        # 旧版把 RAG、总结、对比、改写都注册成 LangChain tool，
        # 由 create_agent 自己决定什么时候调用。
        tools = [
            create_rewrite_query_tool(trace, history),
            create_search_knowledge_base_tool(self.retriever, trace, retrieval_mode, enable_rerank),
            create_summarize_sources_tool(self.retriever, trace, retrieval_mode, enable_rerank),
            create_compare_sources_tool(self.retriever, trace, retrieval_mode, enable_rerank),
        ]

        agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=AGENT_SYSTEM_PROMPT,
        )

        # 把内存历史塞回 messages，这是旧版多轮上下文方式。
        # 新版 LangGraph 则先经过 SQLite load_context 和 LLM manage_context。
        input_messages = history_to_messages(history)
        input_messages.append({"role": "user", "content": question})

        with Timer(trace, "agent_total"):
            result = agent.invoke({"messages": input_messages})

        messages = result.get("messages", [])
        answer = extract_last_ai_message_content(messages)
        trace["answer"] = answer
        trace["message_count"] = len(messages)
        self.session_store.append_turn(session_id, question, answer)

        return {
            "answer": answer,
            "messages": stringify_messages(messages),
            "trace": trace,
            "sources": extract_sources_from_trace(trace),
            "route": "legacy",
        }


def history_to_messages(history: list) -> list[dict]:
    messages: list[dict] = []
    for turn in history:
        messages.append({"role": "user", "content": turn.question})
        messages.append({"role": "assistant", "content": turn.answer})
    return messages


def extract_sources_from_trace(trace: dict) -> list[dict]:
    for event in reversed(trace.get("tool_events", [])):
        retrieval_trace = event.get("retrieval_trace")
        if retrieval_trace and retrieval_trace.get("results"):
            return retrieval_trace["results"]
    return []


def extract_last_ai_message_content(messages: list) -> str:
    for message in reversed(messages):
        content = getattr(message, "content", None)
        if content:
            return str(content)
    return ""


def stringify_messages(messages: list) -> list[dict]:
    result = []
    for message in messages:
        result.append(
            {
                "type": message.__class__.__name__,
                "content": getattr(message, "content", ""),
                "tool_calls": getattr(message, "tool_calls", None),
            }
        )
    return result
