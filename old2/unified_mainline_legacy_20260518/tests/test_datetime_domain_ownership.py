from __future__ import annotations

from mini_rag.capabilities.datetime import resolver as datetime_resolver
from mini_rag.graph import time_contract as legacy_time_contract


def test_datetime_time_contract_is_owned_by_capability_layer() -> None:
    assert datetime_resolver.normalize_time_requirement.__module__ == "mini_rag.capabilities.datetime.resolver"
    assert legacy_time_contract.normalize_time_requirement is datetime_resolver.normalize_time_requirement
    assert legacy_time_contract.apply_weekday_date_if_possible is datetime_resolver.apply_weekday_date_if_possible
