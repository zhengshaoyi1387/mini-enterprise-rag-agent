from mini_rag.agent.context_store import SQLiteContextStore


def test_sqlite_context_store_persists_summary_and_turns_across_instances(tmp_path):
    db_path = tmp_path / "context.sqlite3"
    store = SQLiteContextStore(db_path)
    store.update_summary("s1", "用户在询问智能客服平台。")
    store.append_turn(
        session_id="s1",
        question="智能客服平台有哪些模块？",
        standalone_query="智能客服平台有哪些模块？",
        answer="包含在线会话和知识库。",
        sources=[{"source": "manual.md"}],
        trace={"route": "rag"},
    )

    reloaded = SQLiteContextStore(db_path)
    context = reloaded.get_context("s1", max_turns=3)

    assert context.summary == "用户在询问智能客服平台。"
    assert len(context.turns) == 1
    assert context.turns[0].sources == [{"source": "manual.md"}]


def test_sqlite_context_store_keeps_recent_turns_only(tmp_path):
    store = SQLiteContextStore(tmp_path / "context.sqlite3")
    for index in range(4):
        store.append_turn(
            session_id="s1",
            question=f"q{index}",
            standalone_query=f"q{index}",
            answer=f"a{index}",
            sources=[],
            trace={},
        )

    context = store.get_context("s1", max_turns=2)

    assert [turn.question for turn in context.turns] == ["q2", "q3"]

