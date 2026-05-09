from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from mini_rag.security.permissions import RolePolicyMap, get_allowed_tool_actions, normalize_role

ToolFunc = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    risk_level: str
    func: ToolFunc
    input_schema: dict[str, Any] = field(default_factory=dict)
    action_contracts: dict[str, dict[str, Any]] = field(default_factory=dict)
    examples: list[dict[str, Any]] = field(default_factory=list)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        func: ToolFunc,
        description: str,
        risk_level: str = "low",
        input_schema: dict[str, Any] | None = None,
        action_contracts: dict[str, dict[str, Any]] | None = None,
        examples: list[dict[str, Any]] | None = None,
    ) -> None:
        self._tools[name] = RegisteredTool(
            name=name,
            func=func,
            description=description,
            risk_level=risk_level,
            input_schema=input_schema or {},
            action_contracts=action_contracts or {},
            examples=examples or [],
        )

    def invoke(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        result = tool.func(payload)
        result.setdefault("tool_name", name)
        result.setdefault("risk_level", tool.risk_level)
        return result

    def get(self, name: str | None) -> RegisteredTool | None:
        if not name:
            return None
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "risk_level": tool.risk_level,
                "input_schema": tool.input_schema,
                "action_contracts": tool.action_contracts,
                "examples": tool.examples,
            }
            for tool in self._tools.values()
        ]

    def has_tool(self, name: str | None) -> bool:
        return bool(name and name in self._tools)

    def allowed_actions(self, name: str | None, role: str | None, role_policies: RolePolicyMap | None = None) -> set[str]:
        if not name or name not in self._tools:
            return set()
        return get_allowed_tool_actions(role, name, role_policies=role_policies)

    def format_tool_contracts_for_prompt(self, role: str | None = None, role_policies: RolePolicyMap | None = None) -> str:
        """Return compact permission-aware contracts for the planner.

        This is intentionally not the full JSON Schema. It is the current role's
        capability catalog: tools/actions not visible here should not be planned.
        """
        role = normalize_role(role)
        contracts: list[dict[str, Any]] = []
        for tool in self._tools.values():
            allowed = self.allowed_actions(tool.name, role, role_policies=role_policies)
            if not allowed:
                continue
            actions: dict[str, Any] = {}
            if "*" in allowed:
                actions["*"] = tool.action_contracts.get("*") or self._compact_schema(tool.input_schema)
            else:
                for action in sorted(allowed):
                    if action in tool.action_contracts:
                        actions[action] = tool.action_contracts[action]
            if not actions:
                continue
            contracts.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "risk_level": tool.risk_level,
                    "actions": actions,
                }
            )
        return json.dumps(contracts, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _compact_schema(schema: dict[str, Any]) -> dict[str, Any]:
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if not isinstance(properties, dict):
            return {}
        return {"input_fields": sorted(properties.keys()), "required": schema.get("required", [])}
