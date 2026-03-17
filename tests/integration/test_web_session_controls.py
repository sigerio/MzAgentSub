from pathlib import Path

from .web_testkit import build_test_app, call_app


def test_web_reset_clears_history_and_status(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "搜索协议",
            "action_type": "tool",
            "target": "search_docs",
        },
    )

    reset_response = call_app(app, method="POST", path="/api/session/sess_web_test/reset")
    history_response = call_app(app, method="GET", path="/api/session/sess_web_test/history")
    status_response = call_app(app, method="GET", path="/api/session/sess_web_test/status")

    assert reset_response["status"] == 200
    assert reset_response["json"]["message"] == "当前会话已重置。"
    assert history_response["json"]["history"] == []
    assert status_response["json"]["status_key"] == "idle"
