from __future__ import annotations

from typing import Any, Callable

from mini_rag.graph.prompts import MEMORY_UPDATE_SYSTEM, format_memory_user
from mini_rag.graph.utils import coerce_list, strip_citations_and_metadata, truncate


class MemoryService:
    """Persist compact turn memory without keeping memory logic in nodes."""

    def __init__(
        self,
        *,
        context_store: Any,
        invoke_json: Callable[..., dict[str, Any]],
        build_trace: Callable[[dict[str, Any]], dict[str, Any]],
        should_use_lightweight_memory: Callable[[dict[str, Any]], bool],
        on_complete: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.context_store = context_store
        self._invoke_json = invoke_json
        self._build_trace = build_trace
        self._should_use_lightweight_memory = should_use_lightweight_memory
        self._on_complete = on_complete

    def update_memory(self, state: dict[str, Any]) -> dict[str, Any]:
        answer = state.get("final_answer", "")
        old_summary = state.get("conversation_summary", "")

        if self._should_use_lightweight_memory(state):
            memory_answer = strip_citations_and_metadata(answer)
            topic = state.get("topic", "")
            entities = state.get("entities", [])
            summary = old_summary or ""
        else:
            payload = self._invoke_json(
                state=state,
                node="update_memory",
                system=MEMORY_UPDATE_SYSTEM,
                user=format_memory_user(
                    question=state.get("question", ""),
                    standalone_query=state.get("standalone_query", ""),
                    answer=truncate(answer, 1600),
                    old_summary=old_summary,
                ),
                default={
                    "memory_answer": strip_citations_and_metadata(answer),
                    "summary": old_summary,
                    "topic": state.get("topic", ""),
                    "entities": state.get("entities", []),
                },
            )
            memory_answer = str(payload.get("memory_answer") or strip_citations_and_metadata(answer))
            summary = str(payload.get("summary") or old_summary)
            topic = str(payload.get("topic") or state.get("topic", ""))
            entities = [str(x) for x in coerce_list(payload.get("entities") or state.get("entities", []))]

        state["memory_update"] = {
            "memory_answer": memory_answer,
            "summary": summary,
            "topic": topic,
            "entities": entities,
        }
        session_id = state.get("session_id")
        if session_id:
            self.context_store.update_summary(session_id, summary)
            self.context_store.append_turn(
                session_id=session_id,
                question=state.get("question", ""),
                standalone_query=state.get("standalone_query", state.get("question", "")),
                answer=answer,
                sources=state.get("sources", []),
                trace=self._build_trace(state),
                memory_answer=memory_answer,
                intent=state.get("intent", ""),
                topic=topic,
                entities=entities,
            )
        if self._on_complete is not None:
            self._on_complete(state)
        return state
