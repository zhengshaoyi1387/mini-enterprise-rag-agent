from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mini_rag.skills.models import SkillCard, SkillManifest


class SkillRegistry:
    def __init__(self, base_dir: str | Path = "skills") -> None:
        self.base_dir = Path(base_dir)
        self._skills: dict[str, SkillManifest] = {}
        self.warnings: list[str] = []
        self.scan_skills(self.base_dir)

    @classmethod
    def from_base_dir(cls, base_dir: str | Path = "skills") -> "SkillRegistry":
        return cls(base_dir)

    def scan_skills(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir or self.base_dir)
        self._skills.clear()
        self.warnings.clear()
        if not self.base_dir.exists():
            self.warnings.append(f"skill base dir not found: {self.base_dir}")
            return
        for skill_dir in sorted(path for path in self.base_dir.iterdir() if path.is_dir()):
            manifest_path = skill_dir / "skill.yaml"
            if not manifest_path.exists():
                continue
            try:
                raw = _load_manifest(manifest_path)
                manifest = SkillManifest.from_dict(raw, skill_dir=skill_dir)
                self._skills[manifest.name] = manifest
            except Exception as exc:  # noqa: BLE001 - bad skill config should not break startup
                self.warnings.append(f"{manifest_path}: {exc}")

    def list_skills(self) -> list[SkillManifest]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillManifest | None:
        return self._skills.get(str(name or "").strip())

    def get_skill_card(self, name: str) -> SkillCard | None:
        manifest = self.get_skill(name)
        return manifest.to_card() if manifest else None

    def list_skill_cards(self) -> list[SkillCard]:
        return [manifest.to_card() for manifest in self.list_skills()]

    def find_candidate_skills(self, query: str, intent_tags: list[str] | None = None) -> list[dict[str, Any]]:
        query_text = str(query or "").strip()
        query_tokens = set(_tokens(query_text))
        tag_set = {str(tag).strip().lower() for tag in (intent_tags or []) if str(tag).strip()}
        candidates: list[dict[str, Any]] = []
        for manifest in self.list_skills():
            score = 0.0
            reasons: list[str] = []
            matched_tags = sorted(set(manifest.intent_tags) & tag_set)
            if matched_tags:
                score += 0.5
                reasons.append(f"matched intent tag {', '.join(matched_tags)}")
            example_scores: list[tuple[float, str]] = []
            for example in manifest.trigger_examples:
                example_tokens = set(_tokens(example))
                overlap = len(query_tokens & example_tokens)
                if overlap:
                    denom = max(1, min(len(query_tokens), len(example_tokens)))
                    example_scores.append((overlap / denom, example))
            if example_scores:
                best, example = max(example_scores, key=lambda item: item[0])
                score += min(0.45, best * 0.45)
                reasons.append(f"matched trigger example {example}")
            if score > 0:
                candidates.append(
                    {
                        "name": manifest.name,
                        "score": round(min(score, 1.0), 3),
                        "match_reason": "; ".join(reasons) or "matched skill metadata",
                    }
                )
        return sorted(candidates, key=lambda item: item["score"], reverse=True)


def _load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore[import-not-found]

            raw = yaml.safe_load(text)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("skill.yaml must be JSON-compatible YAML or PyYAML must be installed") from exc
    if not isinstance(raw, dict):
        raise ValueError("skill manifest must be an object")
    return raw


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", lowered)
    output: list[str] = []
    for token in tokens:
        output.append(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{3,}", token):
            output.extend(token[index : index + 2] for index in range(0, max(0, len(token) - 1)))
    return output

