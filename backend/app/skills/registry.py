import re
from pathlib import Path
from typing import Optional

import yaml

from app.core.logging import get_logger
from app.skills.models import SkillDefinition

logger = get_logger(__name__)


class SkillRegistry:
    def __init__(self, skills: list[SkillDefinition]):
        self._skills = sorted(
            [s for s in skills if s.enabled],
            key=lambda s: s.priority,
        )
        logger.info("[SKILL_REGISTRY] loaded %d active skills", len(self._skills))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SkillRegistry":
        path = Path(path)
        if not path.exists():
            logger.warning("[SKILL_REGISTRY] config not found: %s, starting empty", path)
            return cls([])
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        raw_skills = data.get("skills", [])
        skills = [SkillDefinition(**item) for item in raw_skills]
        return cls(skills)

    def match(self, user_input: str) -> Optional[SkillDefinition]:
        if not user_input:
            return None
        lowered = user_input.lower()
        for skill in self._skills:
            if self._is_match(skill, lowered):
                return skill
        return None

    def _is_match(self, skill: SkillDefinition, lowered_input: str) -> bool:
        mode = skill.match.mode
        if mode == "keyword_any":
            return any(kw.lower() in lowered_input for kw in skill.match.keywords)
        if mode == "regex":
            return any(re.search(p, lowered_input, re.IGNORECASE) for p in skill.match.patterns)
        return False
