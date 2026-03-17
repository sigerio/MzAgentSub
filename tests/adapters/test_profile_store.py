from pathlib import Path

from mz_agent.llm_profiles import (
    LLMProfile,
    LLMProfileStore,
    load_profile_store,
    save_profile_store,
)


def test_profile_store_uses_legacy_env_fallback_when_no_file_exists(tmp_path: Path) -> None:
    store = load_profile_store(
        project_root=tmp_path,
        env_values={
            "LLM_MODEL_ID": "gpt-test",
            "LLM_API_KEY": "sk-test",
            "LLM_BASE_URL": "https://example.com/v1",
            "LLM_TIMEOUT": "45",
        },
    )

    assert store.default_profile_name == "default"
    assert len(store.profiles) == 1
    assert store.profiles[0].provider_type == "openai_compatible_proxy"
    assert store.profiles[0].default_model == "gpt-test"


def test_profile_store_can_save_reload_and_switch_default(tmp_path: Path) -> None:
    store = LLMProfileStore(
        default_profile_name="native",
        profiles=[
            LLMProfile(
                profile_name="native",
                display_name="原生方案",
                provider_type="openai_native",
                default_model="gpt-4o-mini",
                api_key="sk-native",
            ),
            LLMProfile(
                profile_name="proxy",
                display_name="反代方案",
                provider_type="openai_compatible_proxy",
                default_model="claude-3-7-sonnet",
                api_key="sk-proxy",
                base_url="https://proxy.example.com/v1",
            ),
        ],
    )
    save_profile_store(project_root=tmp_path, store=store.activate("proxy"))

    reloaded = load_profile_store(project_root=tmp_path, env_values={})

    assert reloaded.default_profile_name == "proxy"
    assert reloaded.require("proxy").base_url == "https://proxy.example.com/v1"
