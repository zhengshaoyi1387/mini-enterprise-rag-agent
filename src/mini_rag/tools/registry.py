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


    def format_tool_routing_summary_for_prompt(self, role: str | None = None, role_policies: RolePolicyMap | None = None) -> str:
        """Return a permission-aware tool summary for request classification.

        This deliberately omits detailed input schemas. The classifier only
        decides whether a tool is needed and which tool/action family applies;
        plan_with_llm receives the full contracts.
        """
        role = normalize_role(role)
        items: list[dict[str, Any]] = []
        for tool in self._tools.values():
            allowed = self.allowed_actions(tool.name, role, role_policies=role_policies)
            if not allowed:
                continue
            actions = sorted(allowed)
            items.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "risk_level": tool.risk_level,
                    "actions": actions,
                }
            )
        return json.dumps(items, ensure_ascii=False, separators=(",", ":"))

    def format_tool_contracts_for_prompt(self, role: str | None = None, role_policies: RolePolicyMap | None = None) -> str:
        """Return compact permission-aware contracts for the planner.

        The planner only needs tool/action names, important field names, and
        safety semantics. Full schema validation is handled later by validators
        and adapters, so this deliberately avoids sending verbose schema values.
        """
        role = normalize_role(role)
        contracts: list[dict[str, Any]] = []
        for tool in self._tools.values():
            allowed = self.allowed_actions(tool.name, role, role_policies=role_policies)
            if not allowed:
                continue
            actions: dict[str, Any] = {}
            if "*" in allowed:
                contract = tool.action_contracts.get("*") or self._compact_schema(tool.input_schema)
                actions["*"] = self._compact_action_contract(contract)
            else:
                for action in sorted(allowed):
                    if action in tool.action_contracts:
                        actions[action] = self._compact_action_contract(tool.action_contracts[action])
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

    def format_scoped_tool_contracts_for_prompt(
        self,
        role: str | None = None,
        role_policies: RolePolicyMap | None = None,
        *,
        selected_tool: str | None = None,
        selected_action: str | None = None,
        include_datetime: bool = False,
    ) -> str:
        """Return only the contracts needed by a specific planning turn.

        The classifier has already chosen a capability family. The detailed
        planner should not see unrelated tools or unrelated write actions,
        because that widens the action space and makes accidental writes easier.
        """

        role = normalize_role(role)
        selected_tool = str(selected_tool or "").strip() or None
        selected_action = str(selected_action or "").strip().lower() or None
        wanted_tools: list[str] = []
        if include_datetime:
            wanted_tools.append("get_current_datetime")
        if selected_tool and selected_tool not in wanted_tools:
            wanted_tools.append(selected_tool)
        if not wanted_tools:
            return self.format_tool_contracts_for_prompt(role=role, role_policies=role_policies)

        contracts: list[dict[str, Any]] = []
        for tool_name in wanted_tools:
            tool = self._tools.get(tool_name)
            if tool is None:
                continue
            allowed = self.allowed_actions(tool.name, role, role_policies=role_policies)
            if not allowed:
                continue
            actions: dict[str, Any] = {}
            if "*" in allowed:
                actions["*"] = tool.action_contracts.get("*") or self._compact_schema(tool.input_schema)
            elif selected_action and selected_action in allowed and selected_action in tool.action_contracts:
                actions[selected_action] = tool.action_contracts[selected_action]
            elif tool.name == selected_tool:
                for action in sorted(allowed):
                    if action in tool.action_contracts:
                        actions[action] = tool.action_contracts[action]
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
    def _compact_action_contract(contract: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(contract, dict):
            return {}
        input_spec = contract.get("in") if isinstance(contract.get("in"), dict) else {}
        fields = sorted(str(key) for key in input_spec.keys()) if isinstance(input_spec, dict) else []
        output: dict[str, Any] = {}
        if fields:
            output["fields"] = fields
        semantics = str(contract.get("semantics") or "").strip()
        if semantics:
            output["semantics"] = semantics
        return output or contract

    @staticmethod
    def _compact_schema(schema: dict[str, Any]) -> dict[str, Any]:
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if not isinstance(properties, dict):
            return {}
        return {"input_fields": sorted(properties.keys()), "required": schema.get("required", [])}
