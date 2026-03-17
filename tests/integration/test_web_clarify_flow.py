from pathlib import Path

from .web_testkit import build_test_app, call_app


def test_web_round_can_surface_clarify_instead_of_system_error(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    round_response = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "帮我处理一下",
            "action_type": "tool",
            "target": None,
        },
    )

    assert round_response["status"] == 200
    assert round_response["json"]["result_type"] == "clarify"
    assert "请补充必要信息" in round_response["json"]["result_text"]
    assert round_response["json"]["status"]["status_key"] == "needs_clarify"


def test_web_invalid_json_and_unknown_session_are_mapped_to_structured_errors(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    invalid_session = call_app(app, method="GET", path="/api/session/unknown/status")
    invalid_request = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={"goal": "   ", "action_type": "llm"},
    )

    assert invalid_session["status"] == 400
    assert invalid_session["json"]["error_code"] == "invalid_request"
    assert invalid_request["status"] == 400
    assert invalid_request["json"]["message"] == "goal 不能为空。"
