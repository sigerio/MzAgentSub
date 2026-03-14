"""MzAgent 第一阶段 Skill 适配壳。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SkillDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    prompt: str
    resource_manifest: dict[str, object] = Field(default_factory=dict)


class SkillAdapter:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDescriptor] = {}

    def register(self, *, skill: SkillDescriptor) -> None:
        self._skills[skill.name] = skill

    def consume(
        self,
        *,
        name: str,
        skill_args: dict[str, object] | None = None,
    ) -> dict[str, object]:
        skill = self._skills.get(name)
        if skill is None:
            return {
                "load_status": "unavailable",
                "error_code": "SKL_001",
                "message": "未找到匹配 Skill。",
            }

        return {
            "selected_skill": skill.name,
            "skill_metadata": {
                "name": skill.name,
                "description": skill.description,
            },
            "skill_prompt": skill.prompt,
            "resource_manifest": skill.resource_manifest,
            "load_status": "loaded",
            "skill_args": skill_args or {},
        }

