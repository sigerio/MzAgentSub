import json
from pathlib import Path

from mz_agent.adapters.llm import LLMAdapter
from mz_agent.contracts.tooling import MCPBinding, ToolExecutionResult
from mz_agent.app import ConversationService, RuntimeOptions
from mz_agent.web import create_app

from .web_testkit import build_test_app, call_app


class ScriptedLLMResponder:
    def __init__(
        self,
        *,
        route_map: dict[str, dict[str, object]] | None = None,
        completion_map: dict[str, str] | None = None,
    ) -> None:
        self.route_map = route_map or {}
        self.completion_map = completion_map or {}
        self.requests = []

    def __call__(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        system_text = request.messages[0].content if request.messages else ""
        user_text = request.messages[-1].content if request.messages else ""
        if "自动编排路由器" in system_text:
            decision = self.route_map.get(
                user_text,
                {
                    "action_type": "llm",
                    "target": None,
                    "arguments": {},
                    "respond_with_llm": True,
                    "expect_user_followup": False,
                    "reason": "默认回退到 LLM。",
                },
            )
            return json.dumps(decision, ensure_ascii=False)
        return self.completion_map.get(user_text, f"LLM 回答：{user_text}")


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
    responder = ScriptedLLMResponder(
        route_map={
            "搜索协议": {
                "action_type": "tool",
                "target": "search_docs",
                "arguments": {"query": "搜索协议"},
                "respond_with_llm": True,
                "expect_user_followup": False,
                "reason": "先检索文档再组织答复。",
            }
        },
        completion_map={"搜索协议": "已基于搜索结果生成最终答复"},
    )
    app = _build_test_app_with_profile_and_llm(
        tmp_path,
        responder=responder,
    )

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
    assert round_response["json"]["result_type"] == "llm"
    assert round_response["json"]["result_text"] == "已基于搜索结果生成最终答复"
    assert round_response["json"]["history"][0]["round_id"] == round_response["json"]["round_id"]
    assert round_response["json"]["history"][1]["round_id"] == round_response["json"]["round_id"]
    assert len(round_response["json"]["history"]) == 2
    assert round_response["json"]["raw_result"]["llm_completion_enforced"] is True
    sources = [
        item["source"]
        for item in round_response["json"]["raw_result"]["intermediate_observations"]
    ]
    assert sources == ["tool"]


def test_web_auto_round_with_empty_skill_list_still_falls_back_to_llm(tmp_path: Path) -> None:
    app = _build_test_app_with_profile_and_llm(
        tmp_path,
        responder=lambda request: "已直接由 LLM 回答",
    )

    round_response = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "帮我整理一下这段话",
            "action_type": "auto",
            "target": None,
            "profile_name": "default",
            "enabled_capabilities": ["skill"],
            "enabled_tools": [],
            "enabled_mcp": [],
            "enabled_skills": [],
            "rag_enabled": False,
        },
    )

    assert round_response["status"] == 200
    assert round_response["json"]["result_type"] == "llm"
    assert round_response["json"]["result_text"] == "已直接由 LLM 回答"
    assert len(round_response["json"]["history"]) == 2


def test_web_auto_round_plain_text_mentioning_cunzhi_does_not_directly_trigger_mcp(tmp_path: Path) -> None:
    responder = ScriptedLLMResponder(
        route_map={
            "用cunzhi向我提问": {
                "action_type": "llm",
                "target": None,
                "arguments": {},
                "respond_with_llm": True,
                "expect_user_followup": False,
                "reason": "这是一条普通自然语言请求，先由 LLM 解释。",
            }
        },
        completion_map={"用cunzhi向我提问": "我可以先理解你的意图，再决定是否需要调用外部能力。"},
    )
    app = _build_test_app_with_profile_and_llm(
        tmp_path,
        responder=responder,
    )

    service = app._service  # type: ignore[attr-defined]
    service._pipeline.adapters.mcp.register(
        binding=MCPBinding(
            server_name="cunzhi",
            transport="stdio",
            tool_name="zhi",
            namespace="cunzhi",
        ),
        handler=lambda message, is_markdown=True: ToolExecutionResult(
            status="success",
            text=f"cunzhi 已收到：{message}",
            data={"is_markdown": is_markdown},
        ),
    )

    round_response = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "用cunzhi向我提问",
            "action_type": "auto",
            "target": None,
            "profile_name": "default",
            "enabled_capabilities": ["mcp"],
            "enabled_tools": [],
            "enabled_mcp": ["cunzhi:zhi"],
            "enabled_skills": [],
            "rag_enabled": False,
        },
    )

    assert round_response["status"] == 200
    assert round_response["json"]["result_type"] == "llm"
    assert round_response["json"]["result_text"] == "我可以先理解你的意图，再决定是否需要调用外部能力。"
    sources = [
        item["source"]
        for item in round_response["json"]["raw_result"]["intermediate_observations"]
    ]
    assert sources == []


def test_web_auto_round_explicit_routed_mcp_runs_and_waits_for_followup(tmp_path: Path) -> None:
    responder = ScriptedLLMResponder(
        route_map={
            "请用外部提问能力向我提一个问题": {
                "action_type": "mcp",
                "target": "cunzhi:zhi",
                "arguments": {"message": "请只向用户提出一个问题。", "is_markdown": True},
                "respond_with_llm": False,
                "expect_user_followup": True,
                "reason": "本轮目标是先向用户追问。",
            },
            "我最担心编排链断裂": {
                "action_type": "llm",
                "target": None,
                "arguments": {},
                "respond_with_llm": True,
                "expect_user_followup": False,
                "reason": "用户已经给出回答，回到主链总结。",
            },
        },
        completion_map={"我最担心编排链断裂": "我已收到你的回答，当前最关键的问题是编排链断裂。"},
    )
    app = _build_test_app_with_profile_and_llm(
        tmp_path,
        responder=responder,
    )

    service = app._service  # type: ignore[attr-defined]
    service._pipeline.adapters.mcp.register(
        binding=MCPBinding(
            server_name="cunzhi",
            transport="stdio",
            tool_name="zhi",
            namespace="cunzhi",
        ),
        handler=lambda message, is_markdown=True: ToolExecutionResult(
            status="success",
            text="你当前最担心什么？",
            data={"received_message": message, "is_markdown": is_markdown},
        ),
    )

    first_round = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "请用外部提问能力向我提一个问题",
            "action_type": "auto",
            "target": None,
            "profile_name": "default",
            "enabled_capabilities": ["mcp"],
            "enabled_tools": [],
            "enabled_mcp": ["cunzhi:zhi"],
            "enabled_skills": [],
            "rag_enabled": False,
        },
    )

    assert first_round["status"] == 200
    assert first_round["json"]["result_type"] == "mcp"
    assert first_round["json"]["result_text"] == "你当前最担心什么？"
    assert first_round["json"]["raw_result"]["pending_external_interaction"]["target"] == "cunzhi:zhi"

    second_round = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "我最担心编排链断裂",
            "action_type": "auto",
            "target": None,
            "profile_name": "default",
            "enabled_capabilities": ["mcp"],
            "enabled_tools": [],
            "enabled_mcp": ["cunzhi:zhi"],
            "enabled_skills": [],
            "rag_enabled": False,
        },
    )

    assert second_round["status"] == 200
    assert second_round["json"]["result_type"] == "llm"
    assert second_round["json"]["result_text"] == "我已收到你的回答，当前最关键的问题是编排链断裂。"
    assert len(second_round["json"]["history"]) == 4
    assert second_round["json"]["history"][-2]["content"] == "我最担心编排链断裂"
    assert second_round["json"]["history"][-1]["content"] == "我已收到你的回答，当前最关键的问题是编排链断裂。"
    completion_request = responder.requests[-1]
    completion_texts = [message.content for message in completion_request.messages]
    assert "你当前最担心什么？" in completion_texts
    assert "我最担心编排链断裂" in completion_texts


def test_web_auto_round_explicit_routed_mcp_error_does_not_block_later_llm_response(tmp_path: Path) -> None:
    responder = ScriptedLLMResponder(
        route_map={
            "请通过外部能力继续追问": {
                "action_type": "mcp",
                "target": "cunzhi:zhi",
                "arguments": {"message": "请继续追问用户。", "is_markdown": True},
                "respond_with_llm": True,
                "expect_user_followup": False,
                "reason": "需要先尝试外部追问，再由 LLM 收口。",
            }
        },
        completion_map={"请通过外部能力继续追问": "尽管 MCP 失败，LLM 仍已完成答复"},
    )
    app = _build_test_app_with_profile_and_llm(
        tmp_path,
        responder=responder,
    )

    service = app._service  # type: ignore[attr-defined]
    service._pipeline.adapters.mcp.register(
        binding=MCPBinding(
            server_name="cunzhi",
            transport="stdio",
            tool_name="zhi",
            namespace="cunzhi",
        ),
        handler=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("cunzhi 临时不可用")),
    )

    round_response = call_app(
        app,
        method="POST",
        path="/api/round",
        payload={
            "goal": "请通过外部能力继续追问",
            "action_type": "auto",
            "target": None,
            "profile_name": "default",
            "enabled_capabilities": ["mcp"],
            "enabled_tools": [],
            "enabled_mcp": ["cunzhi:zhi"],
            "enabled_skills": [],
            "rag_enabled": False,
        },
    )

    assert round_response["status"] == 200
    assert round_response["json"]["result_type"] == "llm"
    assert round_response["json"]["result_text"] == "尽管 MCP 失败，LLM 仍已完成答复"
    assert round_response["json"]["raw_result"]["intermediate_observations"][0]["source"] == "mcp"


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


def _build_test_app_with_profile_and_llm(tmp_path: Path, *, responder):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )
    (tmp_path / ".mz_agent").mkdir()
    (tmp_path / ".mz_agent" / "llm_profiles.json").write_text(
        json.dumps(
            {
                "connection": {
                    "base_url": "https://example.com/v1",
                    "api_key": "sk-test",
                    "timeout": 60,
                },
                "active_profile_name": "default",
                "profiles": [
                    {
                        "profile_name": "default",
                        "display_name": "Default",
                        "model_name": "gpt-test",
                        "api_mode": "openai-responses",
                        "extra_headers": {},
                        "enabled_capabilities": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    options = RuntimeOptions(
        stm_path=".mz_agent/test_web_stm.json",
        session_id="sess_web_test",
        request_prefix="req_web",
        trace_prefix="trace_web",
    )
    service = ConversationService(project_root=tmp_path, options=options)
    service._pipeline.adapters.llm = LLMAdapter(responder=responder)
    return create_app(service=service)
