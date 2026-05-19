from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from mini_rag.capabilities.calendar.lexicon import (
    CALENDAR_QUERY_TERMS,
    EVENT_TYPE_TERMS,
    ORDINAL_SELECTOR_TERMS,
    RELATIVE_DATE_TERMS,
    UPDATE_ACTION_TERMS,
    UPDATE_FIELD_TERMS,
)

EVENT_ID_RE = re.compile(r"EVT-\d{8}-\d{4}", re.IGNORECASE)


@dataclass(frozen=True)
class RelativeCalendarQuery:
    relative: str
    event_type: str
    objective: str


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term in text or term.lower() in lower for term in terms)


def mentions_calendar_query(text: str) -> bool:
    return _contains_any(text, CALENDAR_QUERY_TERMS)


def mentions_update_action(text: str) -> bool:
    return _contains_any(text, UPDATE_ACTION_TERMS)


def infer_event_type(text: str) -> str:
    matched: list[str] = []
    for event_type, terms in EVENT_TYPE_TERMS:
        if _contains_any(text, terms):
            matched.append(event_type)
    return matched[0] if len(set(matched)) == 1 else "all"


def infer_relative_event_queries(text: str) -> list[RelativeCalendarQuery]:
    hits: list[tuple[int, str, str]] = []
    lower = text.lower()
    for relative, terms in RELATIVE_DATE_TERMS:
        for term in terms:
            index = lower.find(term.lower()) if any(ord(ch) < 128 for ch in term) else text.find(term)
            if index >= 0:
                hits.append((index, relative, term))
                break
    if not hits:
        return []
    hits.sort(key=lambda item: item[0])
    queries: list[RelativeCalendarQuery] = []
    for idx, (start, relative, term) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(text)
        segment = text[start:end]
        event_type = infer_event_type(segment)
        if event_type == "all" and len(hits) == 1:
            event_type = infer_event_type(text)
        if event_type == "all" and not mentions_calendar_query(segment):
            continue
        queries.append(
            RelativeCalendarQuery(
                relative=relative,
                event_type=event_type,
                objective=segment.strip("，。,.；; ") or term,
            )
        )
    return queries


def infer_ordinal_selector(text: str) -> str | None:
    for value, terms in ORDINAL_SELECTOR_TERMS:
        if _contains_any(text, terms):
            return value
    return None


def infer_event_id(text: str) -> str | None:
    match = EVENT_ID_RE.search(text or "")
    if not match:
        return None
    return match.group(0).upper()


def _field_after(text: str, field_terms: tuple[str, ...]) -> str | None:
    verbs = "|".join(re.escape(verb) for verb in UPDATE_ACTION_TERMS)
    for term in field_terms:
        pattern = rf"{re.escape(term)}\s*(?:{verbs})\s*([^，。,.；;]+)"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            return value or None
    return None


def infer_update_fields(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field, terms in UPDATE_FIELD_TERMS:
        value = _field_after(text, terms)
        if value:
            fields[field] = value
    if not fields:
        verbs = "|".join(re.escape(verb) for verb in UPDATE_ACTION_TERMS)
        match = re.search(rf"(?:{verbs})\s*([^，。,.；;]+)", text, flags=re.IGNORECASE)
        if match:
            title_value = match.group(1).strip()
            if title_value:
                fields["title"] = title_value
    return fields
