from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mini_rag.infrastructure.db.seed import initialize_enterprise_demo_db
from mini_rag.skills.executor import SkillExecutor
from mini_rag.skills.loader import SkillLoader
from mini_rag.skills.registry import SkillRegistry
from mini_rag.tools.attendance_tool import query_attendance_summary
from mini_rag.tools.calendar_tool import manage_company_calendar
from mini_rag.tools.datetime_tool import get_current_datetime


def main() -> int:
    db_path = ROOT / "data" / "enterprise_demo.db"
    initialize_enterprise_demo_db(db_path, reset=False)

    registry = SkillRegistry(ROOT / "skills")
    executor = SkillExecutor(registry)
    loader = SkillLoader(registry)
    assert {"attendance_insight", "policy_gap_checker"} <= {card.name for card in registry.list_skill_cards()}
    assert loader.load_instruction("attendance_insight").ok

    runtime_context = {
        "user_id": "u004",
        "role": "hr",
        "enterprise_db_path": str(db_path),
        "permissions": ["attendance:read", "rag:read"],
    }
    attendance = executor.execute(
        {
            "skill_name": "attendance_insight",
            "arguments": {"start_date": "2026-05-11", "end_date": "2026-05-17", "group_by": "employee"},
            "runtime_context": runtime_context,
        }
    )
    assert attendance["ok"], attendance
    assert attendance["result"]["total_abnormal_records"] > 0
    assert attendance["trace"]["events"]

    missing = executor.execute(
        {
            "skill_name": "attendance_insight",
            "arguments": {"end_date": "2026-05-17"},
            "runtime_context": runtime_context,
        }
    )
    assert not missing["ok"] and missing["error"]["type"] == "validation_error"

    denied = executor.execute(
        {
            "skill_name": "attendance_insight",
            "arguments": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
            "runtime_context": {**runtime_context, "permissions": []},
        }
    )
    assert not denied["ok"] and denied["error"]["type"] == "permission_denied"

    policy_gap = executor.execute(
        {
            "skill_name": "policy_gap_checker",
            "arguments": {
                "question": "出差酒店费用可以报销吗？流程是什么？",
                "evidence_items": [
                    {
                        "source_id": "finance_001",
                        "title": "差旅报销制度",
                        "content": "报销材料包括行程单、发票、支付凭证。审批流程为直属负责人审批后提交财务复核。",
                    }
                ],
                "required_slots": ["是否可报销", "报销材料", "审批流程"],
            },
            "runtime_context": runtime_context,
        }
    )
    assert policy_gap["ok"], policy_gap
    assert policy_gap["result"]["overall"] == "partial"
    assert "answer" not in policy_gap["result"]

    calendar = manage_company_calendar(
        {
            "action": "query",
            "role": "employee",
            "start_date": "2026-05-20",
            "end_date": "2026-05-20",
            "event_type": "meeting",
            "db_path": str(db_path),
        }
    )
    attendance_tool = query_attendance_summary(
        {
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "status_filters": ["late", "leave", "absent"],
            "db_path": str(db_path),
        }
    )
    datetime_result = get_current_datetime({"fixed_now": "2026-05-21T12:00:00+08:00"})
    assert calendar["events"]
    assert attendance_tool["summary"]["total_records"] > 0
    assert datetime_result["current_date"] == "2026-05-21"

    print(
        json.dumps(
            {
                "ok": True,
                "skills": [card.to_dict() for card in registry.list_skill_cards()],
                "attendance_abnormal": attendance["result"]["total_abnormal_records"],
                "policy_gap_overall": policy_gap["result"]["overall"],
                "trace_events": len(attendance["trace"]["events"]) + len(policy_gap["trace"]["events"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

