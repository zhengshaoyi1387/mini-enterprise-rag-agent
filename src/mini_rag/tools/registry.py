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
        """Return compact tool contracts for LLM tool planning.

        The LLM should decide which tool to call from all available tools.
        ``candidate_tool`` is accepted for backward compatibility but ignored on
        purpose, so keyword hints cannot bias tool selection.
        """
        contracts = [self._compact_contract(tool) for tool in self._tools.values()]
        return json.dumps(contracts, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _compact_contract(tool: RegisteredTool) -> dict[str, Any]:
        """Hand the LLM the smallest useful contract, not full JSON Schema."""
        if tool.name == "get_current_datetime":
            return {
                "name": tool.name,
                "description": tool.description,
                "risk_level": tool.risk_level,
                "input": {"timezone": "Asia/Shanghai"},
                "notes": ["Use to resolve relative dates."],
            }
        if tool.name == "query_attendance_summary":
            return {
                "name": tool.name,
                "description": tool.description,
                "risk_level": tool.risk_level,
                "input": {
                    "start_date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD",
                    "department": "all",
                    "employee_name": None,
                    "group_by": "none|department|employee",
                    "status_filter": "present|late|leave|absent|null",
                    "include_records": False,
                },
                "required": ["start_date", "end_date"],
                "notes": ["include_records=true only when asking who/which employees"],
            }
        if tool.name == "manage_company_calendar":
            return {
                "name": tool.name,
                "description": tool.description,
                "risk_level": tool.risk_level,
                "actions": {
                    "query": {"required": ["action", "start_date", "end_date"], "input": {"action": "query", "start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "event_type": "all", "department": "all"}},
                    "create": {"required": ["action", "title", "date", "time"], "input": {"action": "create", "title": "...", "type": "meeting|training|payday|holiday|activity|maintenance|other", "date": "YYYY-MM-DD", "time": "HH:MM-HH:MM or 全天", "department": "all", "location": "", "description": ""}},
                    "update": {"required": ["action", "event_id"], "input": {"action": "update", "event_id": "EVT-...", "title": "...", "date": "YYYY-MM-DD", "time": "HH:MM-HH:MM"}},
                    "delete": {"required": ["action", "event_id"], "input": {"action": "delete", "event_id": "EVT-..."}},
                },
                "notes": ["action=query/create/update/delete", "create uses date/time, not start_date/end_date", "use time, not start_time/end_time"],
            }
        return {
            "name": tool.name,
            "description": tool.description,
            "risk_level": tool.risk_level,
            "input_schema": tool.input_schema,
        }
