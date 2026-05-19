from __future__ import annotations

from typing import Protocol

from mini_rag.core.contracts import CandidatePlan, CapabilityContract, RequestContext, ValidationResult


class CapabilityHandler(Protocol):
    """Minimal interface implemented by concrete capability domains.

    Handlers may compile a request into a candidate plan, validate candidate
    plans, resolve ambiguous targets, and format deterministic answers. The
    graph layer should depend on this protocol instead of domain-specific
    details.
    """

    name: str
    contract: CapabilityContract

    def compile(self, ctx: RequestContext) -> CandidatePlan | None:
        ...

    def validate(self, plan: CandidatePlan, ctx: RequestContext) -> ValidationResult:
        ...

    def resolve(self, plan: CandidatePlan, ctx: RequestContext) -> CandidatePlan | ValidationResult:
        ...

    def format_answer(self, results: list[dict], ctx: RequestContext) -> str | None:
        ...
