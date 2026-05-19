from __future__ import annotations

"""Compatibility facade for planner contract normalization.

The implementation lives in :mod:`mini_rag.planning.contract_normalizer`.
Graph code imports this module for backward compatibility only; new planning
logic belongs under ``mini_rag.planning`` or the concrete capability domains.
"""

from mini_rag.planning.contract_normalizer import PlanningContractNormalizer

__all__ = ["PlanningContractNormalizer"]
