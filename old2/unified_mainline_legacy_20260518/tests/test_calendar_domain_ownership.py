from __future__ import annotations

from mini_rag.capabilities.calendar import resolver as calendar_resolver
from mini_rag.tools import calendar_resolution as legacy_calendar_resolution


def test_calendar_resolution_logic_is_owned_by_capability_layer() -> None:
    assert calendar_resolver.CalendarTaskResolver.__module__ == "mini_rag.capabilities.calendar.resolver"
    assert legacy_calendar_resolution.CalendarTaskResolver is calendar_resolver.CalendarTaskResolver
    assert legacy_calendar_resolution.select_calendar_events is calendar_resolver.select_calendar_events
