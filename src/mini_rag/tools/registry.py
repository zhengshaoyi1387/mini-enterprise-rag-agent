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
    examples: list[dict[str, Any]] = field(default_factory=list)
    action_contracts: dict[str, dict[str, Any]] = field(default_factory=dict)


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
        examples: list[dict[str, Any]] | None = None,
        action_contracts: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._tools[name] = RegisteredTool(
            name=name,
            func=func,
            description=description,
            risk_level=risk_level,
            input_schema=input_schema or {},
            examples=examples or [],
            action_contracts=action_contracts or {},
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
                "examples": tool.examples,
                "actions": tool.action_contracts,
            }
            for tool in self._tools.values()
        ]

    def has_tool(self, name: str | None) -> bool:
        return bool(name and name in self._tools)

    def format_tool_contracts_for_prompt(
        self,
        role: str | None = None,
        role_policies: RolePolicyMap | None = None,
        candidate_tool: str | None = None,
    ) -> str:
        """Return compact permission-aware tool contracts for LLM planning.

        ``candidate_tool`` is accepted for backward compatibility but ignored on
        purpose, so keyword hints cannot bias tool selection.
        """
        role = normalize_role(role)
        contracts: list[dict[str, Any]] = []
        search_actions = get_allowed_tool_actions(role, "search_knowledge_base", role_policies=role_policies)
        if search_actions:
            contracts.append(
                {
                    "name": "search_knowledge_base",
                    "description": "查询当前角色可访问的企业知识库；制度、流程、FAQ、政策解释和产品文档问题应使用 route=rag。",
                    "risk_level": "low",
                    "actions": {
                        "*": {
                            "input": {"query": "语义完整的知识库检索问题"},
                            "notes": ["route 应为 rag；不要把 search_knowledge_base 作为 daily tool 执行。"],
                        }
                    },
                }
            )
        for tool in self._tools.values():
            allowed_actions = get_allowed_tool_actions(role, tool.name, role_policies=role_policies)
            if not allowed_actions:
                continue
            contracts.append(self._compact_contract(tool, allowed_actions))
        return json.dumps(contracts, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _compact_contract(tool: RegisteredTool, allowed_actions: set[str]) -> dict[str, Any]:
        """Hand the LLM the smallest useful contract, not full JSON Schema."""
        action_contracts = tool.action_contracts
        if allowed_actions != {"*"}:
            action_contracts = {
                action: contract
                for action, contract in action_contracts.items()
                if action in allowed_actions
            }
        if not action_contracts and "*" in allowed_actions:
            action_contracts = {"*": {"input_schema": tool.input_schema}}
        return {
            "name": tool.name,
            "description": tool.description,
            "risk_level": tool.risk_level,
            "actions": action_contracts,
        }
