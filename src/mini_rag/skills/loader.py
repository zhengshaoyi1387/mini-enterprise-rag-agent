from __future__ import annotations

from mini_rag.skills.models import SkillInstruction
from mini_rag.skills.registry import SkillRegistry


class SkillLoader:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def load_instruction(self, skill_name: str) -> SkillInstruction:
        manifest = self.registry.get_skill(skill_name)
        if manifest is None:
            return SkillInstruction(ok=False, skill_name=skill_name, error="skill not found")
        if not manifest.instruction_path.exists():
            return SkillInstruction(ok=False, skill_name=skill_name, error="SKILL.md not found")
        return SkillInstruction(
            ok=True,
            skill_name=manifest.name,
            content=manifest.instruction_path.read_text(encoding="utf-8"),
        )

