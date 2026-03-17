"""MzAgent 第一阶段 Skill 适配壳。"""

from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field


class SkillDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    prompt: str
    directory: str | None = None
    resource_manifest: dict[str, object] = Field(default_factory=dict)


class SkillAdapter:
    def __init__(self, *, skill_roots: list[str | Path] | None = None) -> None:
        self._skills: dict[str, SkillDescriptor] = {}
        self._skill_roots = [Path(root).expanduser().resolve() for root in skill_roots or []]

    def register(self, *, skill: SkillDescriptor) -> None:
        self._skills[skill.name] = skill

    def list_skills(self) -> list[dict[str, object]]:
        discovered = self._discover_candidates()
        names = sorted(set(self._skills) | set(discovered))
        results: list[dict[str, object]] = []
        for name in names:
            if name in self._skills:
                descriptor = self._skills[name]
                results.append(
                    {
                        "name": descriptor.name,
                        "description": descriptor.description,
                        "dir": descriptor.directory,
                    }
                )
                continue
            candidate = discovered[name]
            results.append(
                {
                    "name": name,
                    "description": candidate.get("description"),
                    "dir": str(candidate["directory"]),
                }
            )
        return results

    def list_skill_names(self) -> list[str]:
        return [item["name"] for item in self.list_skills() if isinstance(item.get("name"), str)]

    def consume(
        self,
        *,
        name: str,
        skill_args: dict[str, object] | None = None,
    ) -> dict[str, object]:
        skill = self._skills.get(name)
        if skill is None:
            load_result = self._load_skill_from_roots(name=name)
            if "error_code" in load_result:
                return {
                    "load_status": "unavailable",
                    **load_result,
                }
            skill = load_result["skill"]
            self._skills[skill.name] = skill

        return {
            "selected_skill": skill.name,
            "skill_metadata": {
                "name": skill.name,
                "description": skill.description,
                "dir": skill.directory,
            },
            "skill_prompt": skill.prompt,
            "resource_manifest": skill.resource_manifest,
            "load_status": "loaded",
            "skill_args": skill_args or {},
        }

    def _load_skill_from_roots(self, *, name: str) -> dict[str, object]:
        discovered = self._discover_candidates()
        candidate = discovered.get(name)
        if candidate is None:
            return {
                "error_code": "SKL_001",
                "message": "未找到匹配 Skill。",
            }
        skill_file = candidate["directory"] / "SKILL.md"
        if not skill_file.exists():
            return {
                "error_code": "SKL_002",
                "message": "Skill 装载失败。",
            }
        try:
            content = skill_file.read_text(encoding="utf-8")
        except OSError:
            return {
                "error_code": "SKL_002",
                "message": "Skill 装载失败。",
            }
        frontmatter, prompt = _parse_skill_file(content=content)
        description = frontmatter.get("description")
        if not isinstance(description, str) or not description.strip() or not prompt.strip():
            return {
                "error_code": "SKL_003",
                "message": "Skill 内容不可消费。",
            }
        skill_name = frontmatter.get("name")
        if not isinstance(skill_name, str) or not skill_name.strip():
            return {
                "error_code": "SKL_003",
                "message": "Skill 内容不可消费。",
            }
        return {
            "skill": SkillDescriptor(
                name=skill_name.strip(),
                description=description.strip(),
                prompt=prompt.strip(),
                directory=str(candidate["directory"]),
                resource_manifest=_build_resource_manifest(skill_dir=candidate["directory"]),
            )
        }

    def _discover_candidates(self) -> dict[str, dict[str, object]]:
        discovered: dict[str, dict[str, object]] = {}
        for root in self._skill_roots:
            if not root.exists():
                continue
            for skill_dir in sorted(path for path in root.iterdir() if path.is_dir()):
                discovered[skill_dir.name] = {
                    "directory": skill_dir,
                    "description": _peek_skill_description(skill_dir=skill_dir),
                }
        return discovered


def _peek_skill_description(*, skill_dir: Path) -> str | None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None
    frontmatter, _ = _parse_skill_file(content=content)
    description = frontmatter.get("description")
    return description.strip() if isinstance(description, str) and description.strip() else None


def _parse_skill_file(*, content: str) -> tuple[dict[str, str], str]:
    stripped = content.strip()
    if not stripped.startswith("---"):
        return ({}, stripped)
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return ({}, stripped)
    frontmatter_lines: list[str] = []
    body_start_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start_index = index + 1
            break
        frontmatter_lines.append(line)
    if body_start_index is None:
        return ({}, stripped)
    frontmatter: dict[str, str] = {}
    for line in frontmatter_lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip()
    body = "\n".join(lines[body_start_index:]).strip()
    return (frontmatter, body)


def _build_resource_manifest(*, skill_dir: Path) -> dict[str, object]:
    manifest: dict[str, object] = {}
    for resource_dir_name in ("scripts", "references", "examples", "assets"):
        resource_dir = skill_dir / resource_dir_name
        if not resource_dir.exists():
            continue
        manifest[resource_dir_name] = sorted(
            str(path.relative_to(skill_dir))
            for path in resource_dir.rglob("*")
            if path.is_file()
        )
    return manifest
