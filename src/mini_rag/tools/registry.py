from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

ToolFunc = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    risk_level: str
    func: ToolFunc
    input_schema: dict[str, Any] = field(default_factory=dict)
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
        examples: list[dict[str, Any]] | None = None,
    ) -> None:
        self._tools[name] = RegisteredTool(
            name=name,
            func=func,
            description=description,
            risk_level=risk_level,
            input_schema=input_schema or {},
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
                "examples": tool.examples,
            }
            for tool in self._tools.values()
        ]

    def has_tool(self, name: str | None) -> bool:
        return bool(name and name in self._tools)

    def format_tool_contracts_for_prompt(self, candidate_tool: str | None = None) -> str:
        """Return compact tool contracts for the LLM tool-planning prompt."""
        tools = list(self._tools.values())

        # 候选工具排前面，但仍保留所有工具，避免 LLM 被错误候选绑死。
        if candidate_tool and candidate_tool in self._tools:
            candidate = self._tools[candidate_tool]
            tools = [candidate] + [tool for tool in tools if tool.name != candidate_tool]

        contracts = []
        for tool in tools:
            contracts.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "risk_level": tool.risk_level,
                    "input_schema": tool.input_schema,
                    "examples": tool.examples,
                }
            )

        return json.dumps(contracts, ensure_ascii=False, indent=2)