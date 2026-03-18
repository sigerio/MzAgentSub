from pathlib import Path

from .web_testkit import build_test_app, call_app


def test_profile_api_can_create_activate_and_dispatch_round(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    connection_response = call_app(
        app,
        method="POST",
        path="/api/llm/connection",
        payload={
            "base_url": "https://proxy.example.com/v1",
            "api_key": "sk-proxy-a",
            "timeout": 60,
        },
    )
    assert connection_response["status"] == 200
    assert connection_response["json"]["profiles"]["connection"]["is_configured"] is True

    create_response = call_app(
        app,
        method="POST",
        path="/api/llm/profiles",
        payload={
            "profile_name": "proxy-a",
            "display_name": "反代 A",
            "model_name": "claude-3-7-sonnet",
            "api_mode": "anthropic-messages",
            "extra_headers": {},
            "enabled_capabilities": [],
        },
    )
    assert create_response["status"] == 200
    assert create_response["json"]["profiles"]["active_profile_name"] == "proxy-a"
    profile_names = [
        profile["profile_name"]
        for profile in create_response["json"]["profiles"]["profiles"]
    ]
    assert "proxy-a" in profile_names

    activate_response = call_app(
        app,
        method="POST",
        path="/api/llm/profiles/proxy-a/activate",
    )
    assert activate_response["status"] == 200
    assert activate_response["json"]["profiles"]["active_profile_name"] == "proxy-a"

    list_response = call_app(app, method="GET", path="/api/llm/profiles")
    assert list_response["status"] == 200
    assert list_response["json"]["active_profile_name"] == "proxy-a"
    proxy_profile = next(
        profile
        for profile in list_response["json"]["profiles"]
        if profile["profile_name"] == "proxy-a"
    )
    assert proxy_profile["model_name"] == "claude-3-7-sonnet"
    assert proxy_profile["api_mode"] == "anthropic-messages"
    assert list_response["json"]["connection"]["api_key_masked"] == "sk-p***xy-a"

    round_response = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "你好，返回一句话",
            "action_type": "llm",
            "profile_name": "proxy-a",
        },
    )
    assert round_response["status"] == 200
    assert round_response["json"]["profile_name"] == "proxy-a"
    assert round_response["json"]["status"]["active_profile_name"] == "proxy-a"
    assert round_response["json"]["status"]["result_profile_name"] == "proxy-a"


def test_profile_api_delete_and_reset_session_keep_profiles_separate(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    call_app(
        app,
        method="POST",
        path="/api/llm/connection",
        payload={
            "base_url": "https://proxy.example.com/v1",
            "api_key": "sk-native-2",
            "timeout": 60,
        },
    )
    call_app(
        app,
        method="POST",
        path="/api/llm/profiles",
        payload={
            "profile_name": "native-2",
            "display_name": "GPT 主模型",
            "model_name": "gpt-4o-mini",
            "extra_headers": {},
            "enabled_capabilities": [],
        },
    )
    delete_response = call_app(
        app,
        method="DELETE",
        path="/api/llm/profiles/native-2",
    )
    assert delete_response["status"] == 200
    assert delete_response["json"]["profiles"]["active_profile_name"] is None

    reset_response = call_app(app, method="POST", path="/api/session/sess_web_test/reset")
    assert reset_response["status"] == 200

    list_response = call_app(app, method="GET", path="/api/llm/profiles")
    assert list_response["status"] == 200
    assert list_response["json"]["active_profile_name"] is None
    assert len(list_response["json"]["profiles"]) == 0
