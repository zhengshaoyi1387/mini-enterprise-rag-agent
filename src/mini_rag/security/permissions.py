from __future__ import annotations

"""Centralized endpoint, tool and knowledge-base permission rules.

The key design choice: permissions are assigned at the knowledge-base level.
Chunks only carry ``kb_id`` as metadata so retrieval can be filtered *before*
unauthorized documents reach the model context.
"""

from dataclasses import dataclass
from typing import Final

from mini_rag.ingestion.kb_config import KNOWLEDGE_BASES, normalize_kb_ids


VALID_ROLES: Final[set[str]] = {"guest", "user", "employee", "finance", "hr", "it", "admin"}
DEFAULT_ROLE: Final[str] = "user"

ROLE_ALLOWED_KBS: Final[dict[str, list[str]]] = {
    "admin": ["public", "hr", "finance", "it", "product"],
    "user": ["public", "hr", "it", "product"],
    "employee": ["public", "hr", "it", "product"],
    "finance": ["public", "finance"],
    "hr": ["public", "hr"],
    "it": ["public", "it"],
    "guest": ["public"],
}

ENDPOINT_PERMISSIONS: Final[dict[str, list[str]]] = {
    "health": ["guest", "user", "employee", "finance", "hr", "it", "admin"],
    "query": ["guest", "user", "employee", "finance", "hr", "it", "admin"],
    "chat": ["guest", "user", "employee", "finance", "hr", "it", "admin"],
    "trace": ["admin"],
    "eval": ["admin"],
    "upload": ["user", "employee", "finance", "hr", "it", "admin"],
    "admin_kbs": ["admin"],
    "admin_tools": ["admin"],
    "admin_audit": ["admin"],
}

TOOL_PERMISSIONS: Final[dict[str, list[str]]] = {
    "search_knowledge_base": ["guest", "user", "employee", "finance", "hr", "it", "admin"],
    "summarize_sources": ["guest", "user", "employee", "finance", "hr", "it", "admin"],
    "rewrite_query": ["guest", "user", "employee", "finance", "hr", "it", "admin"],
    "generate_study_plan": ["guest", "user", "employee", "finance", "hr", "it", "admin"],
    "compare_sources": ["user", "employee", "finance", "hr", "it", "admin"],
    "read_memory": ["user", "employee", "finance", "hr", "it", "admin"],
    "save_memory": ["user", "employee", "finance", "hr", "it", "admin"],
    "run_eval": ["admin"],
    "generate_weekly_report": ["user", "employee", "finance", "hr", "it", "admin"],
    "draft_email": ["user", "employee", "finance", "hr", "it", "admin"],
    "create_it_ticket": ["user", "employee", "it", "admin"],
    "check_reimbursement_rule": ["finance", "admin"],
    "generate_leave_request": ["user", "employee", "hr", "admin"],
}


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    role: str
    resource: str
    reason: str


@dataclass(frozen=True)
class RolePolicy:
    role: str
    allowed_kbs: list[str]
    allowed_tools: list[str]


RolePolicyMap = dict[str, RolePolicy]


def normalize_role(role: str | None) -> str:
    normalized = (role or DEFAULT_ROLE).strip().lower()
    if normalized in VALID_ROLES:
        return normalized
    return "guest"


def can_access_endpoint(role: str | None, endpoint_name: str) -> bool:
    role = normalize_role(role)
    return role in ENDPOINT_PERMISSIONS.get(endpoint_name, [])


def can_use_tool(role: str | None, tool_name: str, role_policies: RolePolicyMap | None = None) -> bool:
    role = normalize_role(role)
    if role_policies and role in role_policies:
        return tool_name in role_policies[role].allowed_tools
    return role in TOOL_PERMISSIONS.get(tool_name, [])


def get_allowed_kbs(role: str | None, role_policies: RolePolicyMap | None = None) -> list[str]:
    role = normalize_role(role)
    if role_policies and role in role_policies:
        return normalize_kb_ids(role_policies[role].allowed_kbs)
    return list(ROLE_ALLOWED_KBS.get(role, ROLE_ALLOWED_KBS["guest"]))


def filter_allowed_kbs(role: str | None, requested_kbs: list[str] | None, role_policies: RolePolicyMap | None = None) -> list[str]:
    allowed = set(get_allowed_kbs(role, role_policies=role_policies))
    requested = normalize_kb_ids(requested_kbs)
    if not requested:
        return sorted(allowed)
    return sorted(kb_id for kb_id in requested if kb_id in allowed)


def assert_can_access_kbs(role: str | None, requested_kbs: list[str] | None, role_policies: RolePolicyMap | None = None) -> list[str]:
    allowed_kbs = filter_allowed_kbs(role, requested_kbs, role_policies=role_policies)
    if not allowed_kbs:
        requested = normalize_kb_ids(requested_kbs)
        raise PermissionError(
            f"role={normalize_role(role)} is not allowed to access requested knowledge bases: {requested or requested_kbs}"
        )
    return allowed_kbs


def check_endpoint_permission(role: str | None, endpoint_name: str) -> PermissionDecision:
    role = normalize_role(role)
    allowed = can_access_endpoint(role, endpoint_name)
    reason = "allowed" if allowed else f"role={role} is not allowed to access endpoint={endpoint_name}"
    return PermissionDecision(allowed=allowed, role=role, resource=endpoint_name, reason=reason)


def check_tool_permission(role: str | None, tool_name: str, role_policies: RolePolicyMap | None = None) -> PermissionDecision:
    role = normalize_role(role)
    allowed = can_use_tool(role, tool_name, role_policies=role_policies)
    reason = "allowed" if allowed else f"role={role} is not allowed to use tool={tool_name}"
    return PermissionDecision(allowed=allowed, role=role, resource=tool_name, reason=reason)


def assert_tool_permission(role: str | None, tool_name: str, role_policies: RolePolicyMap | None = None) -> None:
    decision = check_tool_permission(role, tool_name, role_policies=role_policies)
    if not decision.allowed:
        raise PermissionError(decision.reason)


def knowledge_base_permission_summary(role: str | None, role_policies: RolePolicyMap | None = None) -> dict[str, object]:
    role = normalize_role(role)
    allowed = get_allowed_kbs(role, role_policies=role_policies)
    return {
        "role": role,
        "allowed_kbs": allowed,
        "knowledge_bases": [
            {"kb_id": kb_id, **KNOWLEDGE_BASES[kb_id], "allowed": kb_id in allowed}
            for kb_id in KNOWLEDGE_BASES
        ],
    }


def default_role_policy(role: str) -> RolePolicy:
    role = normalize_role(role)
    allowed_tools = sorted(tool for tool, roles in TOOL_PERMISSIONS.items() if role in roles)
    return RolePolicy(role=role, allowed_kbs=get_allowed_kbs(role), allowed_tools=allowed_tools)
