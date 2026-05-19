from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
import time
from typing import Any

from mini_rag.utils import ensure_dir


@dataclass
class ConversationTurn:
    """持久化的一轮对话。

    display answer、memory answer 和 trace 分离：
    - answer：给用户看的完整答案，可包含引用。
    - memory_answer：给下一轮上下文理解用的干净答案，不包含 source/title_path/chunk_id。
    - trace：只用于排查，不参与下一轮语义理解。
    """

    question: str
    answer: str
    standalone_query: str = ""
    memory_answer: str = ""
    intent: str = ""
    topic: str = ""
    entities: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class ConversationContext:
    """一次读取出来的会话上下文。

    - summary 是长期压缩记忆。
    - turns 是最近 N 轮完整问答。

    LangGraph 的 build_runtime_context 节点会读取这个对象，再交给 Planner。
    """

    session_id: str | None
    summary: str
    turns: list[ConversationTurn]


class SQLiteContextStore:
    """SQLite 上下文存储，替代进程内 InMemorySessionStore。

    设计目标是“本地真实持久化”：不需要 Redis 等外部服务，但重启服务后仍能按
    session_id 找回摘要和最近几轮对话。
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        # SQLite 文件通常放在 storage/ 下。第一次运行时目录可能不存在，所以先创建。
        ensure_dir(self.db_path.parent)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        # row_factory 让查询结果可以用 row["字段名"] 读取，比 row[0] 更清楚。
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """初始化 SQLite 表。

        sessions：每个 session 一行，保存会话摘要。
        turns：每轮问答一行，保存原问题、独立问题、答案、引用来源和 trace。

        为什么 summary 和 turns 分开？
        - summary 是“压缩后的长期记忆”，每次更新覆盖即可。
        - turns 是“完整历史记录”，需要按时间追加，方便追溯。
        """
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL DEFAULT '',
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    standalone_query TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    trace_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    memory_answer TEXT NOT NULL DEFAULT '',
                    intent TEXT NOT NULL DEFAULT '',
                    topic TEXT NOT NULL DEFAULT '',
                    entities_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_session_id_id ON turns(session_id, id)")
            existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(turns)").fetchall()}
            migrations = {
                "memory_answer": "ALTER TABLE turns ADD COLUMN memory_answer TEXT NOT NULL DEFAULT ''",
                "intent": "ALTER TABLE turns ADD COLUMN intent TEXT NOT NULL DEFAULT ''",
                "topic": "ALTER TABLE turns ADD COLUMN topic TEXT NOT NULL DEFAULT ''",
                "entities_json": "ALTER TABLE turns ADD COLUMN entities_json TEXT NOT NULL DEFAULT '[]'",
            }
            for column, ddl in migrations.items():
                if column not in existing_columns:
                    conn.execute(ddl)

    def get_context(self, session_id: str | None, max_turns: int) -> ConversationContext:
        """读取某个 session 的摘要和最近 N 轮历史。

        如果 session_id 为空，表示这是一次匿名单轮问答，不做长期上下文。
        """
        if not session_id:
            return ConversationContext(session_id=None, summary="", turns=[])

        with self._connect() as conn:
            session_row = conn.execute(
                "SELECT summary FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            # 先按 id 倒序取最近 N 条，再在 Python 里 reversed 回正常时间顺序。
            # 这样返回给 LLM 的历史仍然是从旧到新，比较符合阅读习惯。
            rows = conn.execute(
                """
                SELECT question, standalone_query, answer, sources_json, trace_json, created_at, memory_answer, intent, topic, entities_json
                FROM turns
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, max_turns),
            ).fetchall()

        turns = [
            ConversationTurn(
                question=row["question"],
                standalone_query=row["standalone_query"],
                answer=row["answer"],
                memory_answer=str(row["memory_answer"] or ""),
                intent=str(row["intent"] or ""),
                topic=str(row["topic"] or ""),
                entities=json.loads(row["entities_json"] or "[]"),
                sources=json.loads(row["sources_json"]),
                trace=json.loads(row["trace_json"]),
                created_at=float(row["created_at"]),
            )
            for row in reversed(rows)
        ]
        return ConversationContext(
            session_id=session_id,
            summary=str(session_row["summary"]) if session_row else "",
            turns=turns,
        )

    def update_summary(self, session_id: str | None, summary: str) -> None:
        """更新某个 session 的会话摘要。

        使用 SQLite 的 UPSERT：
        - session 不存在时插入。
        - session 已存在时更新 summary 和 updated_at。
        """
        if not session_id:
            return
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(session_id, summary, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET summary = excluded.summary, updated_at = excluded.updated_at
                """,
                (session_id, summary, now),
            )

    def append_turn(
        self,
        session_id: str | None,
        question: str,
        standalone_query: str,
        answer: str,
        sources: list[dict[str, Any]],
        trace: dict[str, Any],
        memory_answer: str = "",
        intent: str = "",
        topic: str = "",
        entities: list[str] | None = None,
    ) -> None:
        """追加一轮问答历史。

        这里保存的不只是 question/answer，还包括：
        - standalone_query：LLM 改写后的独立检索问题。
        - sources：最终引用来源。
        - trace：本轮 LangGraph 节点执行记录。
        """
        if not session_id:
            return
        # 确保 sessions 表里有这一行。summary 保持当前值不变。
        self.update_summary(session_id, self.get_context(session_id, max_turns=0).summary)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO turns(
                    session_id, question, standalone_query, answer, sources_json, trace_json, created_at,
                    memory_answer, intent, topic, entities_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    question,
                    standalone_query,
                    answer,
                    json.dumps(sources, ensure_ascii=False),
                    json.dumps(trace, ensure_ascii=False),
                    time.time(),
                    memory_answer or "",
                    intent or "",
                    topic or "",
                    json.dumps(entities or [], ensure_ascii=False),
                ),
            )
