from __future__ import annotations

"""Small tool registry for enterprise office tools.

All tool execution goes through this registry so the LangGraph node can apply
permission checks, write trace, and keep tool behavior testable.
"""

from dataclasses import dataclass
from typing import Any, Callable

ToolFunc = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    risk_level: str
    func: ToolFunc


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, name: str, func: ToolFunc, description: str, risk_level: str = "low") -> None:
        self._tools[name] = RegisteredTool(name=name, func=func, description=description, risk_level=risk_level)

    def invoke(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: {name}")
        result = tool.func(payload)
        result.setdefault("tool_name", name)
        result.setdefault("risk_level", tool.risk_level)
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": tool.name, "description": tool.description, "risk_level": tool.risk_level}
            for tool in self._tools.values()
        ]

    def has_tool(self, name: str | None) -> bool:
        return bool(name and name in self._tools)
