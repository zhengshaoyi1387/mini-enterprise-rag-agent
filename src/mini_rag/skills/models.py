from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SkillCard:
    name: str
    version: str
    description: str
    capability_type: str
    risk_level: str
    intent_tags: list[str]
    trigger_examples: list[str]
    not_for: list[str]
    required_permissions: list[str]
    input_schema_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capability_type": self.capability_type,
            "risk_level": self.risk_level,
            "intent_tags": list(self.intent_tags),
            "trigger_examples": list(self.trigger_examples),
            "not_for": list(self.not_for),
            "required_permissions": list(self.required_permissions),
            "input_schema_summary": dict(self.input_schema_summary),
        }


@dataclass(frozen=True)
class SkillManifest:
    name: str
    version: str
    description: str
    capability_type: str
    risk_level: str
    owner: str
    entrypoint: str
    timeout_seconds: int
    intent_tags: list[str] = field(default_factory=list)
    trigger_examples: list[str] = field(default_factory=list)
    not_for: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    eval_cases: list[dict[str, Any]] = field(default_factory=list)
    skill_dir: Path = Path(".")

    @classmethod
    def from_dict(cls, raw: dict[str, Any], skill_dir: Path) -> "SkillManifest":
        required = ("name", "version", "description", "capability_type", "risk_level", "entrypoint")
        missing = [field for field in required if not str(raw.get(field) or "").strip()]
        if missing:
            raise ValueError(f"skill manifest missing required fields: {', '.join(missing)}")
        timeout = int(raw.get("timeout_seconds") or 5)
        if timeout <= 0:
            timeout = 5
        return cls(
            name=str(raw["name"]).strip(),
            version=str(raw["version"]).strip(),
            description=str(raw["description"]).strip(),
            capability_type=str(raw["capability_type"]).strip(),
            risk_level=str(raw["risk_level"]).strip(),
            owner=str(raw.get("owner") or "demo").strip(),
            entrypoint=str(raw["entrypoint"]).strip(),
            timeout_seconds=timeout,
            intent_tags=[str(item).strip() for item in raw.get("intent_tags") or [] if str(item).strip()],
            trigger_examples=[str(item).strip() for item in raw.get("trigger_examples") or [] if str(item).strip()],
            not_for=[str(item).strip() for item in raw.get("not_for") or [] if str(item).strip()],
            required_permissions=[str(item).strip() for item in raw.get("required_permissions") or [] if str(item).strip()],
            required_tools=[str(item).strip() for item in raw.get("required_tools") or [] if str(item).strip()],
            input_schema=dict(raw.get("input_schema") or {}),
            output_schema=dict(raw.get("output_schema") or {}),
            eval_cases=[dict(item) for item in raw.get("eval_cases") or [] if isinstance(item, dict)],
            skill_dir=skill_dir,
        )

    @property
    def entrypoint_path(self) -> Path:
        return self.skill_dir / self.entrypoint

    @property
    def instruction_path(self) -> Path:
        return self.skill_dir / "SKILL.md"

    def to_card(self) -> SkillCard:
        properties = self.input_schema.get("properties") if isinstance(self.input_schema, dict) else {}
        summary: dict[str, Any] = {
            "required": list(self.input_schema.get("required") or []),
            "properties": {},
        }
        if isinstance(properties, dict):
            for name, spec in properties.items():
                if not isinstance(spec, dict):
                    continue
                field_summary = {"type": spec.get("type")}
                if spec.get("enum"):
                    field_summary["enum"] = spec.get("enum")
                if spec.get("description"):
                    field_summary["description"] = spec.get("description")
                summary["properties"][name] = field_summary
        return SkillCard(
            name=self.name,
            version=self.version,
            description=self.description,
            capability_type=self.capability_type,
            risk_level=self.risk_level,
            intent_tags=list(self.intent_tags),
            trigger_examples=list(self.trigger_examples[:3]),
            not_for=list(self.not_for),
            required_permissions=list(self.required_permissions),
            input_schema_summary=summary,
        )


@dataclass(frozen=True)
class SkillInstruction:
    ok: bool
    skill_name: str
    content: str = ""
    error: str | None = None

