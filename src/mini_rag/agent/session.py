from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class ConversationTurn:
    """一轮对话记录。

    这里只保存 question / answer 两个字段，是为了保持 demo 简洁。
    真正生产系统还可能保存 user_id、时间戳、引用来源、token 用量等。
    """

    question: str
    answer: str


class InMemorySessionStore:
    """轻量内存会话，适合 demo 展示多轮追问，不承担生产持久化。

    新手理解：
    session_id 就像聊天窗口编号。同一个 session_id 下，系统会记住最近几轮问答。
    当用户问“它呢？”“上一条呢？”这种追问时，Agent 可以看到之前的上下文。

    为什么叫 InMemory？
    因为数据只存在当前 Python 进程内，服务重启就会丢失。
    这对面试演示足够；生产系统一般会换成 Redis、数据库或 LangGraph checkpoint。
    """

    def __init__(self, max_turns: int = 6):
        # max_turns 控制每个 session 最多保留几轮，避免上下文无限增长。
        self.max_turns = max_turns
        self._sessions: dict[str, list[ConversationTurn]] = {}
        # FastAPI 可能同时处理多个请求；简单加锁，避免并发读写同一个 dict 时出问题。
        self._lock = Lock()

    def get_history(self, session_id: str | None) -> list[ConversationTurn]:
        """读取某个会话的历史；没有 session_id 时表示单轮问答。"""
        if not session_id:
            return []
        with self._lock:
            # 返回 list 副本，避免调用方不小心修改内部存储。
            return list(self._sessions.get(session_id, []))

    def append_turn(self, session_id: str | None, question: str, answer: str) -> None:
        """把本轮问答追加到会话历史。"""
        if not session_id:
            return
        with self._lock:
            turns = self._sessions.setdefault(session_id, [])
            turns.append(ConversationTurn(question=question, answer=answer))
            if len(turns) > self.max_turns:
                # 只保留最近 max_turns 轮。旧对话太多会浪费 token，也可能干扰当前问题。
                del turns[: len(turns) - self.max_turns]


# 模块级默认 store：API 每次创建 EnterpriseKnowledgeAgent 时仍能共享同一份内存会话。
default_session_store = InMemorySessionStore()
