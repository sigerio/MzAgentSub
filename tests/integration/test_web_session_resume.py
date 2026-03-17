from pathlib import Path

from .web_testkit import build_test_app, call_app


def test_web_status_and_history_can_resume_from_stm(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "先搜索协议",
            "action_type": "tool",
            "target": "search_docs",
        },
    )
    call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "再搜索测试",
            "action_type": "tool",
            "target": "search_docs",
        },
    )

    history_response = call_app(app, method="GET", path="/api/session/sess_web_test/history")
    status_response = call_app(app, method="GET", path="/api/session/sess_web_test/status")

    assert history_response["status"] == 200
    assert len(history_response["json"]["history"]) == 4
    assert history_response["json"]["history"][-1]["content"] == "已执行搜索：再搜索测试"
    assert status_response["status"] == 200
    assert status_response["json"]["history_count"] == 4
    assert status_response["json"]["result_type"] == "tool"
