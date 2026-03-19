from pathlib import Path

from .web_testkit import build_test_app, call_app


def test_web_index_and_roundtrip_render_history(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    index_response = call_app(app, method="GET", path="/")
    assert index_response["status"] == 200
    assert "MzAgent" in index_response["text"]
    assert "连接设置" in index_response["text"]
    assert "sess_web_test" in index_response["text"]

    round_response = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "搜索协议",
            "action_type": "tool",
            "target": "search_docs",
        },
    )

    assert round_response["status"] == 200
    assert round_response["json"]["result_type"] == "tool"
    assert round_response["json"]["profile_name"] == "default"
    assert "已执行搜索：搜索协议" in round_response["json"]["result_text"]
    assert len(round_response["json"]["history"]) == 2
