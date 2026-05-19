from __future__ import annotations

from mini_rag.answer.packet import build_answer_packet


def test_answer_packet_keeps_only_compact_task_results_and_sources() -> None:
    state = {
        "route": "rag",
        "task_results": [
            {
                "kind": "rag",
                "objective": "查询报销制度",
                "status": "ok",
                "sources": [
                    {
                        "source": "finance.md",
                        "title_path": "报销制度",
                        "chunk_id": "fin-1",
                        "preview": "发票真实有效，字段完整。",
                        "raw_debug": "不应进入 answer packet",
                    }
                ],
            }
        ],
        "sources": [{"source": "finance.md", "chunk_id": "fin-1", "preview": "发票真实有效，字段完整。"}],
        "tool_result": {"raw": "不应进入 answer packet"},
        "previous_tool_context": {"events": [{"event_id": "EVT-20260518-0001"}]},
    }

    packet = build_answer_packet(state)

    assert packet.route == "rag"
    assert packet.should_call_llm is True
    assert packet.sources[0]["source"] == "finance.md"
    packet_text = str(packet)
    assert "raw_debug" not in packet_text
    assert "previous_tool_context" not in packet_text
    assert "tool_result" not in packet_text


def test_answer_packet_marks_mixed_empty_rag_as_partial_without_candidate_body() -> None:
    state = {
        "route": "rag",
        "task_results": [
            {
                "task_id": "calendar",
                "kind": "tool",
                "status": "ok",
                "tool_name": "manage_company_calendar",
                "action": "query",
                "tool_result": {"events": [{"title": "周会", "date": "2026-05-18"}]},
            },
            {
                "task_id": "policy",
                "kind": "rag",
                "status": "empty",
                "objective": "介绍公司的报销制度",
                "query": "公司报销制度",
                "sources": [],
                "candidate_sources": [
                    {
                        "source": "hr.md",
                        "title_path": "HR FAQ",
                        "preview": "这段候选正文不应进入 AnswerPacket。",
                    }
                ],
            },
        ],
        "sources": [],
        "candidate_sources": [{"preview": "这段候选正文不应进入 AnswerPacket。"}],
    }

    packet = build_answer_packet(state)

    assert packet.status == "partial"
    packet_text = str(packet)
    assert "当前可访问知识库未找到明确支持证据" in packet_text
    assert "这段候选正文不应进入 AnswerPacket" not in packet_text
