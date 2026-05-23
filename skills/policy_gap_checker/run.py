from __future__ import annotations

import json
import sys
from typing import Any

FULL = "full"
PARTIAL = "partial"
MISSING = "missing"

MATERIAL_TERMS = ["行程单", "发票", "支付凭证", "审批记录", "凭证", "材料", "附件", "单据", "报销单"]
APPROVAL_PARTIAL_TERMS = ["审批记录", "直属负责人审批", "负责人审批", "审批要求", "审批"]
APPROVAL_FULL_TERMS = ["审批流程", "审批节点", "流转", "步骤", "财务复核", "专业团队复核", "发起申请"]
ENTRY_TERMS = ["发起申请", "系统", "工单", "入口", "提交", "申请单", "申请方式", "提交平台"]
TIME_TERMS = ["工作日", "时限", "截止", "月结", "18:00", "2个工作日", "2 个工作日", "处理时限", "提交时限", "期限"]
ALLOW_CONCLUSION_TERMS = ["可以报销", "可报销", "允许报销", "属于报销范围", "允许", "可以", "不可以报销", "不可报销", "禁止报销", "不允许"]
CONDITION_TERMS = ["适用", "条件", "范围", "标准", "阈值", "金额", "超过", "低于", "单笔"]
POLICY_TERMS = ["制度", "政策", "规则", "条款", "文档编号", "正式版"]


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    args = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
    question = str(args.get("question") or "")
    topic_terms = _infer_topic_terms(question)
    evidence_items = [item for item in (args.get("evidence_items") or []) if isinstance(item, dict)]
    slots = [str(item).strip() for item in (args.get("required_slots") or []) if str(item).strip()]

    covered_slots: list[dict[str, Any]] = []
    partial_slots: list[dict[str, Any]] = []
    missing_slots: list[dict[str, Any]] = []

    for slot in slots:
        assessment = _assess_slot(slot, evidence_items, topic_terms=topic_terms)
        if assessment["coverage_level"] == FULL:
            covered_slots.append(assessment)
        elif assessment["coverage_level"] == PARTIAL:
            partial_slots.append(assessment)
        else:
            missing_slots.append(assessment)

    if covered_slots and not partial_slots and not missing_slots:
        overall = "full"
    elif covered_slots or partial_slots:
        overall = "partial"
    else:
        overall = "none"

    result = {
        "covered_slots": covered_slots,
        "partial_slots": partial_slots,
        "missing_slots": missing_slots,
        "overall": overall,
        "limitations": [
            "该 Skill 只做证据覆盖分析，不直接生成最终制度结论。",
            "最终是否可回答仍以 RAG Evidence Judge 和 Answer LLM 的结果为准。",
        ],
    }
    print(json.dumps(result, ensure_ascii=False))


def _infer_topic_terms(question: str) -> list[str]:
    text = str(question or "")
    topic_groups = [
        (("酒店", "住宿", "酒店费用", "酒店花费", "房费"), ["酒店", "住宿", "酒店费用", "酒店花费", "房费"]),
        (("机票", "交通", "打车", "车票", "高铁", "火车"), ["机票", "交通", "打车", "车票", "高铁", "火车"]),
        (("餐费", "餐饮", "招待", "餐补"), ["餐费", "餐饮", "招待", "餐补"]),
        (("会议室", "会议", "预订"), ["会议室", "会议", "预订"]),
    ]
    for triggers, terms in topic_groups:
        if any(term in text for term in triggers):
            return terms
    return []


def _assess_slot(slot: str, evidence_items: list[dict[str, Any]], *, topic_terms: list[str]) -> dict[str, Any]:
    text_by_source = _text_by_source(evidence_items)
    combined_text = "\n".join(text_by_source.values())
    slot_norm = slot.strip()

    if slot_norm in {"所需材料", "报销材料", "凭证要求"}:
        return _coverage_from_terms(
            slot_norm,
            text_by_source,
            MATERIAL_TERMS,
            full_threshold=4,
            partial_summary="证据提到部分报销材料，但没有完整说明该场景的材料清单。",
            full_summary="证据较完整覆盖了报销材料要求。",
            topic_terms=topic_terms,
        )

    if slot_norm == "审批流程":
        full_terms = _matched_terms(combined_text, APPROVAL_FULL_TERMS)
        partial_terms = _matched_terms(combined_text, APPROVAL_PARTIAL_TERMS + APPROVAL_FULL_TERMS)
        topic_terms_found = _matched_terms(combined_text, topic_terms)
        has_multiple_flow_nodes = len(set(full_terms)) >= 2 or (
            "发起申请" in full_terms and any(term in full_terms for term in ("财务复核", "专业团队复核", "审批节点"))
        )
        if has_multiple_flow_nodes:
            level = FULL if _topic_allows_full(topic_terms, topic_terms_found) else PARTIAL
            summary = "证据包含多个流程节点，较完整覆盖审批流程。" if level == FULL else _topic_partial_summary("审批流程", topic_terms)
            return _covered(slot_norm, text_by_source, full_terms + topic_terms_found, level, summary)
        if partial_terms:
            return _covered(slot_norm, text_by_source, partial_terms + topic_terms_found, PARTIAL, "证据包含审批相关信号，但不足以构成完整流程。")
        return _missing(slot_norm, "现有证据没有明确覆盖审批流程。")

    if slot_norm == "申请入口或发起方式":
        return _coverage_from_terms(
            slot_norm,
            text_by_source,
            ENTRY_TERMS,
            full_threshold=3,
            partial_summary="证据提到申请/提交相关信号，但没有完整说明入口或发起方式。",
            full_summary="证据覆盖了申请入口或发起方式。",
            topic_terms=topic_terms,
        )

    if slot_norm in {"提交或处理时限", "时间要求"}:
        return _coverage_from_terms(
            slot_norm,
            text_by_source,
            TIME_TERMS,
            full_threshold=2,
            partial_summary="证据提到时间或时限信号，但没有完整说明该场景处理时限。",
            full_summary="证据覆盖了提交或处理时限。",
            topic_terms=topic_terms,
        )

    if slot_norm in {"是否允许", "是否可报销", "核心结论", "明确政策条款"}:
        if slot_norm == "明确政策条款":
            conclusion = _matched_terms(combined_text, ALLOW_CONCLUSION_TERMS)
            policy = _matched_terms(combined_text, POLICY_TERMS)
            topic_terms_found = _matched_terms(combined_text, topic_terms)
            if conclusion and policy and _topic_allows_full(topic_terms, topic_terms_found):
                return _covered(slot_norm, text_by_source, conclusion + policy + topic_terms_found, FULL, "证据包含明确结论和政策条款信号。")
            if policy or conclusion:
                return _covered(slot_norm, text_by_source, policy + conclusion + topic_terms_found, PARTIAL, "证据包含政策或结论相关信号，但不足以形成完整明确条款。")
            return _missing(slot_norm, "现有证据没有明确覆盖政策条款。")
        conclusion_terms = _matched_terms(combined_text, ALLOW_CONCLUSION_TERMS)
        topic_terms_found = _matched_terms(combined_text, topic_terms)
        # Material requirements alone do not prove that a specific hotel expense is reimbursable.
        if conclusion_terms and _topic_allows_full(topic_terms, topic_terms_found):
            return _covered(slot_norm, text_by_source, conclusion_terms + topic_terms_found, FULL, "证据包含是否允许/是否可报销的结论性表达。")
        if conclusion_terms:
            return _covered(slot_norm, text_by_source, conclusion_terms + topic_terms_found, PARTIAL, _topic_partial_summary(slot_norm, topic_terms))
        return _missing(slot_norm, f"现有证据没有明确覆盖「{slot_norm}」的结论。")

    if slot_norm in {"适用条件", "操作要求"}:
        return _coverage_from_terms(
            slot_norm,
            text_by_source,
            CONDITION_TERMS,
            full_threshold=2,
            partial_summary=f"证据提到与「{slot_norm}」相关的条件信号，但不完整。",
            full_summary=f"证据较完整覆盖「{slot_norm}」。",
            topic_terms=topic_terms,
        )

    return _coverage_from_terms(
        slot_norm,
        text_by_source,
        [slot_norm],
        full_threshold=1,
        partial_summary=f"证据提到「{slot_norm}」相关信号，但覆盖不完整。",
        full_summary=f"证据覆盖「{slot_norm}」。",
        topic_terms=topic_terms,
    )


def _text_by_source(evidence_items: list[dict[str, Any]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for index, item in enumerate(evidence_items, start=1):
        source_id = str(item.get("source_id") or item.get("id") or f"evidence_{index}")
        output[source_id] = " ".join(str(item.get(field) or "") for field in ("title", "content", "preview", "summary"))
    return output


def _matched_terms(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term and term in text]


def _source_ids_for_terms(text_by_source: dict[str, str], terms: list[str]) -> list[str]:
    ids: list[str] = []
    for source_id, text in text_by_source.items():
        if any(term in text for term in terms):
            ids.append(source_id)
    return ids


def _topic_allows_full(topic_terms: list[str], topic_terms_found: list[str]) -> bool:
    return not topic_terms or bool(topic_terms_found)


def _topic_partial_summary(slot: str, topic_terms: list[str]) -> str:
    if not topic_terms:
        return f"证据提到与「{slot}」相关的信号，但覆盖不完整。"
    topic_label = "/".join(topic_terms[:3])
    return f"证据提到与「{slot}」相关的通用信号，但没有明确绑定当前核心对象（{topic_label}），因此只能作为部分覆盖。"


def _coverage_from_terms(
    slot: str,
    text_by_source: dict[str, str],
    terms: list[str],
    *,
    full_threshold: int,
    partial_summary: str,
    full_summary: str,
    topic_terms: list[str] | None = None,
) -> dict[str, Any]:
    combined_text = "\n".join(text_by_source.values())
    matched = _matched_terms(combined_text, terms)
    if not matched:
        return _missing(slot, f"现有证据没有明确覆盖「{slot}」。")
    topic_terms = topic_terms or []
    topic_terms_found = _matched_terms(combined_text, topic_terms)
    enough_slot_evidence = len(set(matched)) >= full_threshold
    topic_allows_full = _topic_allows_full(topic_terms, topic_terms_found)
    level = FULL if enough_slot_evidence and topic_allows_full else PARTIAL
    if level == FULL:
        summary = full_summary
    elif enough_slot_evidence and not topic_allows_full:
        summary = _topic_partial_summary(slot, topic_terms)
    else:
        summary = partial_summary
    return _covered(slot, text_by_source, matched + topic_terms_found, level, summary)


def _covered(slot: str, text_by_source: dict[str, str], terms: list[str], level: str, summary: str) -> dict[str, Any]:
    unique_terms = list(dict.fromkeys(terms))
    return {
        "slot": slot,
        "covered": level == FULL,
        "coverage_level": level,
        "evidence_source_ids": _source_ids_for_terms(text_by_source, unique_terms),
        "evidence_terms": unique_terms,
        "summary": summary,
    }


def _missing(slot: str, reason: str) -> dict[str, Any]:
    return {"slot": slot, "covered": False, "coverage_level": MISSING, "reason": reason}


if __name__ == "__main__":
    main()
