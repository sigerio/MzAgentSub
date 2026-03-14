from pathlib import Path

from mz_agent.adapters.skill import SkillAdapter, SkillDescriptor


def test_skill_adapter_returns_loaded_payload_with_manifest_and_args() -> None:
    adapter = SkillAdapter()
    adapter.register(
        skill=SkillDescriptor(
            name="writer",
            description="写作技能",
            prompt="请按要求写作",
            resource_manifest={"templates": ["outline.md"]},
        )
    )

    result = adapter.consume(
        name="writer",
        skill_args={"tone": "formal"},
    )

    assert result == {
        "selected_skill": "writer",
        "skill_metadata": {
            "name": "writer",
            "description": "写作技能",
            "dir": None,
        },
        "skill_prompt": "请按要求写作",
        "resource_manifest": {"templates": ["outline.md"]},
        "load_status": "loaded",
        "skill_args": {"tone": "formal"},
    }


def test_skill_adapter_returns_unavailable_for_missing_skill() -> None:
    adapter = SkillAdapter()

    result = adapter.consume(name="missing")

    assert result == {
        "load_status": "unavailable",
        "error_code": "SKL_001",
        "message": "未找到匹配 Skill。",
    }


def test_skill_adapter_scans_directory_and_exposes_manifest(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"
    writer_dir = skill_root / "writer"
    (writer_dir / "scripts").mkdir(parents=True)
    (writer_dir / "references").mkdir()
    (writer_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: writer",
                "description: 写作技能",
                "---",
                "",
                "请先整理提纲，再开始写作。",
            ]
        ),
        encoding="utf-8",
    )
    (writer_dir / "scripts" / "outline.py").write_text("print('ok')\n", encoding="utf-8")
    (writer_dir / "references" / "style.md").write_text("# 风格\n", encoding="utf-8")

    adapter = SkillAdapter(skill_roots=[skill_root])

    assert adapter.list_skills() == [
        {
            "name": "writer",
            "description": "写作技能",
            "dir": str(writer_dir.resolve()),
        }
    ]
    assert adapter.consume(name="writer", skill_args={"tone": "formal"}) == {
        "selected_skill": "writer",
        "skill_metadata": {
            "name": "writer",
            "description": "写作技能",
            "dir": str(writer_dir.resolve()),
        },
        "skill_prompt": "请先整理提纲，再开始写作。",
        "resource_manifest": {
            "references": ["references/style.md"],
            "scripts": ["scripts/outline.py"],
        },
        "load_status": "loaded",
        "skill_args": {"tone": "formal"},
    }


def test_skill_adapter_returns_load_failure_for_missing_skill_file(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"
    (skill_root / "broken").mkdir(parents=True)

    adapter = SkillAdapter(skill_roots=[skill_root])

    assert adapter.consume(name="broken") == {
        "load_status": "unavailable",
        "error_code": "SKL_002",
        "message": "Skill 装载失败。",
    }


def test_skill_adapter_returns_unconsumable_for_invalid_frontmatter(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"
    broken_dir = skill_root / "broken"
    broken_dir.mkdir(parents=True)
    (broken_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: broken",
                "---",
                "",
                "",
            ]
        ),
        encoding="utf-8",
    )

    adapter = SkillAdapter(skill_roots=[skill_root])

    assert adapter.consume(name="broken") == {
        "load_status": "unavailable",
        "error_code": "SKL_003",
        "message": "Skill 内容不可消费。",
    }
