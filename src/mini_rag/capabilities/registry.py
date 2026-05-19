from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from mini_rag.capabilities.base import CapabilityHandler
from mini_rag.capabilities.contracts import CAPABILITY_CONTRACTS
from mini_rag.core.contracts import CandidatePlan, CapabilityContract, RequestContext, TaskResult, ValidationIssue, ValidationResult


@dataclass(frozen=True)
class ContractCapabilityHandler:
    """Default domain handler backed by a capability contract.

    Concrete domains can override individual methods, but the registry can
    already enforce role gates and deterministic formatting through this base
    handler. That keeps graph code dependent on the capability interface rather
    than calendar/attendance implementation details.
    """

    contract: CapabilityContract

    @property
    def name(self) -> str:
        return self.contract.name

    def compile(self, ctx: RequestContext) -> CandidatePlan | None:
        del ctx
        return None

    def validate(self, plan: CandidatePlan, ctx: RequestContext) -> ValidationResult:
        if ctx.role not in self.contract.allowed_roles:
            return ValidationResult(
                status="refused",
                issues=(
                    ValidationIssue(
                        code="role_not_allowed",
                        message=f"role {ctx.role} cannot use capability {self.name}",
                        layer="validator",
                    ),
                ),
                reason=f"{self.name} refused by capability contract",
            )
        return ValidationResult(status="valid")

    def resolve(self, plan: CandidatePlan, ctx: RequestContext) -> CandidatePlan | ValidationResult:
        validation = self.validate(plan, ctx)
        return plan if validation.ok else validation

    def format_answer(self, results: list[dict] | list[TaskResult], ctx: RequestContext) -> str | None:
        del ctx
        for item in results:
            if isinstance(item, TaskResult):
                summary = item.result_summary
            elif isinstance(item, dict):
                summary = str(item.get("result_summary") or item.get("summary") or "")
            else:
                summary = ""
            if summary:
                return summary
        return None


@dataclass(frozen=True)
class CapabilityRegistry:
    """Registry for capability contracts and their executable handlers."""

    _contracts: tuple[CapabilityContract, ...]
    _handlers: tuple[CapabilityHandler, ...]

    def contracts(self) -> tuple[CapabilityContract, ...]:
        return self._contracts

    def names(self) -> tuple[str, ...]:
        return tuple(contract.name for contract in self._contracts)

    def get(self, name: str) -> CapabilityContract | None:
        normalized = str(name or "").strip()
        for contract in self._contracts:
            if contract.name == normalized:
                return contract
        return None

    def require(self, name: str) -> CapabilityContract:
        contract = self.get(name)
        if contract is None:
            raise KeyError(f"Unknown capability contract: {name}")
        return contract

    def handlers(self) -> tuple[CapabilityHandler, ...]:
        return self._handlers

    def handler_names(self) -> tuple[str, ...]:
        return tuple(handler.name for handler in self._handlers)

    def get_handler(self, name: str) -> CapabilityHandler | None:
        normalized = str(name or "").strip()
        for handler in self._handlers:
            if handler.name == normalized:
                return handler
        return None

    def require_handler(self, name: str) -> CapabilityHandler:
        handler = self.get_handler(name)
        if handler is None:
            raise KeyError(f"Unknown capability handler: {name}")
        return handler

    def visible_contracts(self, *, role: str) -> tuple[CapabilityContract, ...]:
        normalized = str(role or "").strip()
        return tuple(contract for contract in self._contracts if normalized in contract.allowed_roles)

    def compile(self, ctx: RequestContext) -> tuple[CandidatePlan, ...]:
        plans: list[CandidatePlan] = []
        for handler in self._handlers:
            if ctx.role not in handler.contract.allowed_roles:
                continue
            plan = handler.compile(ctx)
            if plan is not None:
                plans.append(plan)
        return tuple(plans)

    def validate(self, capability_name: str, plan: CandidatePlan, ctx: RequestContext) -> ValidationResult:
        return self.require_handler(capability_name).validate(plan, ctx)

    def resolve(self, capability_name: str, plan: CandidatePlan, ctx: RequestContext) -> CandidatePlan | ValidationResult:
        return self.require_handler(capability_name).resolve(plan, ctx)

    def format_answer(self, capability_name: str, results: list[dict] | list[TaskResult], ctx: RequestContext) -> str | None:
        return self.require_handler(capability_name).format_answer(results, ctx)

    def template_answer_contracts(self) -> tuple[CapabilityContract, ...]:
        return tuple(
            contract
            for contract in self._contracts
            if any("template" in policy.lower() for policy in contract.answer_policy)
            or contract.name in {"datetime", "calendar_query", "calendar_write", "attendance_query"}
        )

    def llm_answer_contracts(self) -> tuple[CapabilityContract, ...]:
        return tuple(
            contract
            for contract in self._contracts
            if contract.name == "rag_qa"
            or any("llm" in policy.lower() or "rag" in policy.lower() for policy in contract.answer_policy)
        )


def default_capability_registry(
    extra_contracts: Iterable[CapabilityContract] = (),
    extra_handlers: Iterable[CapabilityHandler] = (),
) -> CapabilityRegistry:
    contracts = tuple(CAPABILITY_CONTRACTS) + tuple(extra_contracts)
    seen: set[str] = set()
    unique: list[CapabilityContract] = []
    for contract in contracts:
        if contract.name in seen:
            continue
        seen.add(contract.name)
        unique.append(contract)
    handler_by_name: dict[str, CapabilityHandler] = {contract.name: ContractCapabilityHandler(contract) for contract in unique}
    for handler in extra_handlers:
        handler_by_name[handler.name] = handler
    handlers = tuple(handler_by_name[contract.name] for contract in unique if contract.name in handler_by_name)
    return CapabilityRegistry(tuple(unique), handlers)
