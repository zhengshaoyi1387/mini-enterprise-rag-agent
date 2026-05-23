from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mini_rag.tools.repositories.attendance_repository import AttendanceRepository

ABNORMAL_STATUSES = {"late", "leave", "absent"}
STATUSES = ("present", "late", "leave", "absent")
RISK_LEVEL_ORDER = {"low": 1, "medium": 2, "high": 3}


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    args = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
    runtime_context = payload.get("runtime_context") if isinstance(payload.get("runtime_context"), dict) else {}

    start_date = str(args.get("start_date") or "").strip()
    end_date = str(args.get("end_date") or "").strip()
    group_by = str(args.get("group_by") or "employee").strip().lower()
    if group_by not in {"employee", "department", "status"}:
        group_by = "employee"
    include_normal = bool(args.get("include_normal", False))
    db_path = Path(
        str(
            runtime_context.get("enterprise_db_path")
            or os.environ.get("MINI_RAG_ENTERPRISE_DB_PATH")
            or "data/enterprise_demo.db"
        )
    )

    rows = AttendanceRepository(db_path).query_records(start_date, end_date)
    total_records = len(rows)
    abnormal_rows = [row for row in rows if _status(row) in ABNORMAL_STATUSES]
    employee_items = _group_rows(rows, "employee", include_normal=False)
    department_items = _group_rows(rows, "department", include_normal=False)
    selected_items = _group_rows(rows, group_by, include_normal=include_normal)

    overview = _build_overview(total_records, abnormal_rows, employee_items, department_items)
    rankings = _build_rankings(employee_items, department_items)
    patterns = _build_patterns(employee_items, department_items, overview)
    risk_flags = _build_risk_flags(patterns, employee_items, department_items)
    suggested_followups = _build_suggested_followups(rankings, risk_flags)

    result = {
        "period": {"start_date": start_date, "end_date": end_date},
        "group_by": group_by,
        # Keep old top-level fields for backward compatibility.
        "total_records": total_records,
        "total_abnormal_records": len(abnormal_rows),
        "overview": overview,
        "items": selected_items,
        "rankings": rankings,
        "patterns": patterns,
        "risk_flags": risk_flags,
        "suggested_followups": suggested_followups,
        "limitations": [
            "本结果基于当前 demo SQLite attendance_records 数据生成。",
            "该 Skill 只做统计分析和风险提示，不做考勤审批或记录修改。",
            "风险提示基于固定规则生成，不代表正式 HR 处置结论。",
        ],
    }
    print(json.dumps(result, ensure_ascii=False))


def _status(row: dict[str, Any]) -> str:
    return str(row.get("status") or "").lower()


def _count_abnormal_types(item: dict[str, Any]) -> int:
    return sum(1 for status in ABNORMAL_STATUSES if int(item.get(f"{status}_count") or 0) > 0)


def _pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00%"
    return f"{numerator / denominator * 100:.2f}%"


def _group_rows(rows: list[dict[str, Any]], group_by: str, *, include_normal: bool) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {f"{status}_count": 0 for status in STATUSES})
    metadata: dict[str, dict[str, str]] = {}
    for row in rows:
        status = _status(row)
        if status not in STATUSES:
            continue
        if group_by == "department":
            key = str(row.get("department") or "-")
            metadata.setdefault(key, {"department": key})
        elif group_by == "status":
            key = status
            metadata.setdefault(key, {"status": status})
        else:
            key = str(row.get("employee_id") or "")
            metadata.setdefault(
                key,
                {
                    "employee_id": key,
                    "name": str(row.get("name") or ""),
                    "department": str(row.get("department") or ""),
                },
            )
        groups[key][f"{status}_count"] += 1

    items: list[dict[str, Any]] = []
    for key, counts in sorted(groups.items()):
        abnormal_total = sum(int(counts.get(f"{status}_count", 0)) for status in ABNORMAL_STATUSES)
        if not include_normal and abnormal_total == 0:
            continue
        total = sum(int(counts.get(f"{status}_count", 0)) for status in STATUSES)
        item = {
            **metadata.get(key, {}),
            **counts,
            "total_records": total,
            "abnormal_total": abnormal_total,
            "abnormal_rate": _pct(abnormal_total, total),
        }
        if not include_normal:
            item.pop("present_count", None)
        items.append(item)
    return items


def _build_overview(
    total_records: int,
    abnormal_rows: list[dict[str, Any]],
    employee_items: list[dict[str, Any]],
    department_items: list[dict[str, Any]],
) -> dict[str, Any]:
    abnormal_departments = {str(row.get("department") or "") for row in abnormal_rows if row.get("department")}
    return {
        "total_records": total_records,
        "total_abnormal_records": len(abnormal_rows),
        "abnormal_employee_count": len(employee_items),
        "abnormal_department_count": len(abnormal_departments),
        "abnormal_rate": _pct(len(abnormal_rows), total_records),
        "status_breakdown": dict(Counter(_status(row) for row in abnormal_rows)),
        "department_count": len(department_items),
    }


def _rank_items(items: list[dict[str, Any]], key: str, *, limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda item: (-int(item.get(key) or 0), str(item.get("name") or item.get("department") or "")))
    output: list[dict[str, Any]] = []
    for rank, item in enumerate([item for item in ranked if int(item.get(key) or 0) > 0][:limit], start=1):
        compact = {
            field: item.get(field)
            for field in (
                "employee_id",
                "name",
                "department",
                "late_count",
                "leave_count",
                "absent_count",
                "abnormal_total",
                "abnormal_rate",
            )
            if item.get(field) not in (None, "", [], {})
        }
        compact["rank"] = rank
        output.append(compact)
    return output


def _rank_departments(items: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda item: (-int(item.get("abnormal_total") or 0), str(item.get("department") or "")))
    output: list[dict[str, Any]] = []
    for rank, item in enumerate([item for item in ranked if int(item.get("abnormal_total") or 0) > 0][:limit], start=1):
        output.append(
            {
                "rank": rank,
                "department": item.get("department"),
                "abnormal_total": int(item.get("abnormal_total") or 0),
                "late_count": int(item.get("late_count") or 0),
                "leave_count": int(item.get("leave_count") or 0),
                "absent_count": int(item.get("absent_count") or 0),
                "abnormal_rate": item.get("abnormal_rate"),
            }
        )
    return output


def _build_rankings(employee_items: list[dict[str, Any]], department_items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "top_abnormal_employees": _rank_items(employee_items, "abnormal_total"),
        "top_late_employees": _rank_items(employee_items, "late_count"),
        "top_absent_employees": _rank_items(employee_items, "absent_count"),
        "top_departments_by_abnormal_count": _rank_departments(department_items),
    }


def _build_patterns(
    employee_items: list[dict[str, Any]],
    department_items: list[dict[str, Any]],
    overview: dict[str, Any],
) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for item in employee_items:
        name = str(item.get("name") or item.get("employee_id") or "")
        if int(item.get("late_count") or 0) >= 2:
            patterns.append(
                {
                    "type": "repeated_late",
                    "subject_type": "employee",
                    "subject": name,
                    "employee_id": item.get("employee_id"),
                    "level": "medium",
                    "evidence": f"周期内迟到 {int(item.get('late_count') or 0)} 次",
                }
            )
        if int(item.get("absent_count") or 0) >= 2:
            patterns.append(
                {
                    "type": "repeated_absent",
                    "subject_type": "employee",
                    "subject": name,
                    "employee_id": item.get("employee_id"),
                    "level": "high",
                    "evidence": f"周期内缺勤 {int(item.get('absent_count') or 0)} 次",
                }
            )
        if _count_abnormal_types(item) >= 2:
            kinds = [status for status in ("late", "leave", "absent") if int(item.get(f"{status}_count") or 0) > 0]
            patterns.append(
                {
                    "type": "mixed_abnormal",
                    "subject_type": "employee",
                    "subject": name,
                    "employee_id": item.get("employee_id"),
                    "level": "medium",
                    "evidence": f"同一周期内同时出现 {', '.join(kinds)} 异常",
                }
            )

    total_abnormal = int(overview.get("total_abnormal_records") or 0)
    if total_abnormal > 0 and department_items:
        ranked = sorted(department_items, key=lambda item: -int(item.get("abnormal_total") or 0))
        top = ranked[0]
        top_count = int(top.get("abnormal_total") or 0)
        second_count = int(ranked[1].get("abnormal_total") or 0) if len(ranked) > 1 else 0
        ratio = top_count / total_abnormal if total_abnormal else 0
        if top_count > 0 and (ratio >= 0.4 or top_count >= second_count + 2):
            patterns.append(
                {
                    "type": "department_concentration",
                    "subject_type": "department",
                    "subject": top.get("department"),
                    "level": "medium" if ratio < 0.6 else "high",
                    "evidence": f"该部门异常 {top_count} 次，占全部异常 {_pct(top_count, total_abnormal)}",
                }
            )
    return patterns


def _build_risk_flags(
    patterns: list[dict[str, Any]],
    employee_items: list[dict[str, Any]],
    department_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    risks: dict[tuple[str, str], dict[str, Any]] = {}
    for pattern in patterns:
        subject_type = str(pattern.get("subject_type") or "")
        subject = str(pattern.get("subject") or "")
        if not subject:
            continue
        level = str(pattern.get("level") or "low")
        key = (subject_type, subject)
        existing = risks.get(key)
        if existing is None or RISK_LEVEL_ORDER.get(level, 0) > RISK_LEVEL_ORDER.get(str(existing.get("level") or "low"), 0):
            risks[key] = {
                "level": level,
                "subject_type": subject_type,
                "subject": subject,
                "reason": _risk_reason(str(pattern.get("type") or "")),
                "evidence": pattern.get("evidence"),
            }
    # Add light risk for top employees when no pattern-specific risk was emitted.
    for item in sorted(employee_items, key=lambda x: -int(x.get("abnormal_total") or 0))[:3]:
        if int(item.get("abnormal_total") or 0) <= 0:
            continue
        key = ("employee", str(item.get("name") or item.get("employee_id") or ""))
        risks.setdefault(
            key,
            {
                "level": "low",
                "subject_type": "employee",
                "subject": key[1],
                "reason": "周期内存在考勤异常",
                "evidence": f"异常合计 {int(item.get('abnormal_total') or 0)} 次",
            },
        )
    return sorted(risks.values(), key=lambda item: (-RISK_LEVEL_ORDER.get(str(item.get("level") or "low"), 0), str(item.get("subject") or "")))[:8]


def _risk_reason(pattern_type: str) -> str:
    return {
        "repeated_late": "同一周期内重复迟到，需要关注是否存在持续性出勤问题",
        "repeated_absent": "同一周期内重复缺勤，建议优先核查原因",
        "mixed_abnormal": "同一周期出现多类异常，建议结合明细进一步确认",
        "department_concentration": "异常集中在单一部门，建议按部门复盘排班或流程原因",
    }.get(pattern_type, "周期内存在考勤异常")


def _build_suggested_followups(rankings: dict[str, Any], risk_flags: list[dict[str, Any]]) -> list[str]:
    followups = [
        "是否查看异常最多员工最近一个月的迟到或缺勤趋势？",
        "是否按部门生成考勤异常周报？",
    ]
    if risk_flags:
        followups.append("是否查看风险提示中员工或部门的原始考勤明细？")
    elif rankings.get("top_late_employees"):
        followups.append("是否查看迟到记录明细？")
    return followups[:3]


if __name__ == "__main__":
    main()
