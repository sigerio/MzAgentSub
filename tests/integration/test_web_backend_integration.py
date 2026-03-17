from pathlib import Path

from .web_testkit import build_test_app, call_app


def test_capability_api_can_list_create_toggle_and_delete_items(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    list_response = call_app(app, method="GET", path="/api/capabilities/tool")
    assert list_response["status"] == 200
    assert list_response["json"]["capability_type"] == "tool"
    assert any(item["name"] == "search_docs" for item in list_response["json"]["items"])

    create_response = call_app(
        app,
        method="POST",
        path="/api/capabilities/skill",
        payload={
            "name": "writer",
            "description": "写作技能",
            "enabled": True,
            "entry": "skills/writer",
        },
    )
    assert create_response["status"] == 200
    assert any(item["name"] == "writer" for item in create_response["json"]["items"])

    toggle_response = call_app(
        app,
        method="POST",
        path="/api/capabilities/skill/writer/toggle",
    )
    assert toggle_response["status"] == 200
    writer = next(item for item in toggle_response["json"]["items"] if item["name"] == "writer")
    assert writer["enabled"] is False

    delete_response = call_app(
        app,
        method="DELETE",
        path="/api/capabilities/skill/writer",
    )
    assert delete_response["status"] == 200
    assert all(item["name"] != "writer" for item in delete_response["json"]["items"])


def test_web_round_accepts_auto_mode_capability_payload(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    round_response = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "搜索协议",
            "action_type": "auto",
            "target": None,
            "profile_name": "default",
            "enabled_capabilities": ["tool"],
            "enabled_tools": ["search_docs"],
            "enabled_mcp": [],
            "enabled_skills": [],
            "rag_enabled": False,
        },
    )

    assert round_response["status"] == 200
    assert round_response["json"]["round_id"].startswith("round_")
    assert round_response["json"]["result_type"] == "tool"
    assert "已执行搜索：搜索协议" in round_response["json"]["result_text"]
    assert round_response["json"]["history"][0]["round_id"] == round_response["json"]["round_id"]
    assert round_response["json"]["history"][1]["round_id"] == round_response["json"]["round_id"]


def test_retry_endpoint_replays_target_round_and_discards_later_history(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)

    first_round = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "先搜索协议",
            "action_type": "tool",
            "target": "search_docs",
        },
    )
    second_round = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "再搜索测试",
            "action_type": "tool",
            "target": "search_docs",
        },
    )
    assert second_round["status"] == 200

    retry_response = call_app(
        app,
        method="POST",
        path=f"/api/session/sess_web_test/rounds/{first_round['json']['round_id']}/retry",
    )

    assert retry_response["status"] == 200
    assert retry_response["json"]["retry_from_round_id"] == first_round["json"]["round_id"]
    assert retry_response["json"]["result_text"] == "已执行搜索：先搜索协议"
    assert len(retry_response["json"]["history"]) == 2
    assert retry_response["json"]["history"][-1]["content"] == "已执行搜索：先搜索协议"


def test_sse_endpoint_returns_current_session_snapshot(tmp_path: Path) -> None:
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

    stream_response = call_app(
        app,
        method="GET",
        path="/api/agent/stream?session_id=sess_web_test",
    )

    assert stream_response["status"] == 200
    assert b"text/event-stream" in stream_response["headers"][b"content-type"]
    assert "event: session_ready" in stream_response["text"]
    assert "event: session_status" in stream_response["text"]
    assert "event: session_history" in stream_response["text"]
