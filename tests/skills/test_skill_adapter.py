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
