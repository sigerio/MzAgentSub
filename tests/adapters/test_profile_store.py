from pathlib import Path

from mz_agent.llm_profiles import (
    LLMConnection,
    LLMProfile,
    LLMProfileStore,
    load_profile_store,
    save_profile_store,
)


def test_profile_store_returns_empty_store_when_file_missing(tmp_path: Path) -> None:
    store = load_profile_store(project_root=tmp_path, env_values={})

    assert store.active_profile_name is None
    assert store.connection is None
    assert store.profiles == []


def test_profile_store_can_save_reload_and_switch_active_model(tmp_path: Path) -> None:
    store = LLMProfileStore(
        connection=LLMConnection(
            base_url="https://proxy.example.com/v1",
            api_key="sk-proxy",
            timeout=45,
        ),
        active_profile_name="gpt-main",
        profiles=[
            LLMProfile(
                profile_name="gpt-main",
                display_name="GPT 主模型",
                model_name="gpt-4.1",
            ),
            LLMProfile(
                profile_name="claude-main",
                display_name="Claude 主模型",
                model_name="claude-3-7-sonnet",
            ),
        ],
    )
    save_profile_store(project_root=tmp_path, store=store.activate("claude-main"))

    reloaded = load_profile_store(project_root=tmp_path, env_values={})

    assert reloaded.active_profile_name == "claude-main"
    assert reloaded.connection is not None
    assert reloaded.connection.base_url == "https://proxy.example.com/v1"
    assert reloaded.require("claude-main").model_name == "claude-3-7-sonnet"
    assert reloaded.require("claude-main").api_mode == "openai-responses"
