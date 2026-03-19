import sys
import types
from pathlib import Path

from mz_agent.adapters import AdapterHub
from mz_agent.adapters.llm import LLMAdapter
from mz_agent.adapters.mcp import MCPAdapter
from mz_agent.capabilities import build_default_capability_registry
from mz_agent.config import load_runtime_settings
from mz_agent.contracts.action import NextAction
from mz_agent.contracts.context import ExecutionContext
from mz_agent.contracts.llm import LLMMessage, LLMRequest
from mz_agent.contracts.tooling import ToolExecutionResult
from mz_agent.http_headers import DEFAULT_USER_AGENT


def test_runtime_settings_load_profile_store_and_mcp_server_from_project_root(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.0.1"

[mcp_servers.cunzhi]
type = "stdio"
command = "/tmp/cz.exe"
tool_timeout_sec = 12.5
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / ".mz_agent").mkdir()
    (tmp_path / ".mz_agent" / "llm_profiles.json").write_text(
        """
{
  "connection": {
    "base_url": "https://example.com/v1",
    "api_key": "sk-test",
    "timeout": 45
  },
  "active_profile_name": "gpt-test",
  "profiles": [
    {
      "profile_name": "gpt-test",
      "display_name": "GPT Test",
      "model_name": "gpt-test",
      "extra_headers": {},
      "enabled_capabilities": []
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    settings = load_runtime_settings(tmp_path)

    assert settings.active_profile_name == "gpt-test"
    assert settings.llm.profile_name == "gpt-test"
    assert settings.llm.model_id == "gpt-test"
    assert settings.llm.api_key == "sk-test"
    assert settings.llm.base_url == "https://example.com/v1"
    assert settings.llm.api_mode == "openai-responses"
    assert settings.llm.timeout == 45
    assert settings.mcp_servers["cunzhi"].command == "/tmp/cz.exe"
    assert settings.mcp_servers["cunzhi"].tool_timeout_sec == 12.5


def test_default_capability_registry_discovers_mcp_tools_without_service_name_special_case(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.0.1"

[mcp_servers.review]
type = "stdio"
command = "/tmp/review.exe"
tool_timeout_sec = 10
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / ".mz_agent").mkdir()
    (tmp_path / ".mz_agent" / "llm_profiles.json").write_text(
        """
{
  "connection": {
    "base_url": "https://example.com/v1",
    "api_key": "sk-test",
    "timeout": 45
  },
  "active_profile_name": "gpt-test",
  "profiles": [
    {
      "profile_name": "gpt-test",
      "display_name": "GPT Test",
      "model_name": "gpt-test",
      "extra_headers": {},
      "enabled_capabilities": []
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "mz_agent.capabilities.MCPAdapter.list_capabilities",
        lambda self, server_name: [
            {
                "server_name": server_name,
                "tool_name": "ask",
                "namespace": server_name,
                "transport": "stdio",
                "description": "继续追问用户",
            }
        ],
    )

    registry = build_default_capability_registry(project_root=tmp_path)

    assert registry.mcp[0].name == "review:ask"
    assert registry.mcp[0].description == "继续追问用户"


def test_llm_adapter_maps_provider_response_to_contracts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )
    (tmp_path / ".mz_agent").mkdir()
    (tmp_path / ".mz_agent" / "llm_profiles.json").write_text(
        """
{
  "connection": {
    "base_url": "https://example.com/v1",
    "api_key": "sk-test",
    "timeout": 60
  },
  "active_profile_name": "gpt-real",
  "profiles": [
    {
      "profile_name": "gpt-real",
      "display_name": "GPT Real",
      "model_name": "gpt-real",
      "extra_headers": {},
      "enabled_capabilities": []
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    class FakeResponsesAPI:
        def create(self, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["model"] == "gpt-real"
            assert kwargs["input"] == [{"role": "user", "content": "你好"}]
            assert "instructions" not in kwargs
            assert "tools" not in kwargs

            text_part = type("TextPart", (), {"type": "output_text", "text": "真实返回"})()
            function_call = type(
                "FunctionCall",
                (),
                {
                    "type": "function_call",
                    "id": "fc_001",
                    "call_id": "call_001",
                    "name": "search_docs",
                    "arguments": '{"query":"协议"}',
                },
            )()
            output_message = type("OutputMessage", (), {"content": [text_part]})()
            usage = type(
                "Usage",
                (),
                {"input_tokens": 7, "output_tokens": 5, "total_tokens": 12},
            )()
            return type(
                "Response",
                (),
                {
                    "id": "resp_001",
                    "_request_id": "req_openai_001",
                    "output_text": "真实返回",
                    "output": [output_message, function_call],
                    "usage": usage,
                    "status": "completed",
                },
            )()

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponsesAPI()

    adapter = LLMAdapter(
        project_root=tmp_path,
        client_factory=lambda settings: FakeClient(),
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="llm",
    )

    result = adapter.respond(
        request=LLMRequest(
            messages=[LLMMessage(role="user", content="你好")],
            model_policy="quality",
        ),
        execution_context=execution_context,
    )

    assert result.content_blocks[0].content == "真实返回"
    assert result.tool_calls == [
        {
            "id": "fc_001",
            "call_id": "call_001",
            "name": "search_docs",
            "arguments": '{"query":"协议"}',
        }
    ]
    assert result.usage is not None
    assert result.usage.total_tokens == 12
    assert result.provider_trace is not None
    assert result.provider_trace.provider == "newapi"
    assert result.provider_trace.api_mode == "openai-responses"
    assert result.provider_trace.profile_name == "gpt-real"
    assert result.raw_response_meta["response_id"] == "resp_001"


def test_llm_adapter_can_dispatch_chat_completions_mode(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )
    (tmp_path / ".mz_agent").mkdir()
    (tmp_path / ".mz_agent" / "llm_profiles.json").write_text(
        """
{
  "connection": {
    "base_url": "https://example.com/v1",
    "api_key": "sk-test",
    "timeout": 60
  },
  "active_profile_name": "gpt-chat",
  "profiles": [
    {
      "profile_name": "gpt-chat",
      "display_name": "GPT Chat",
      "model_name": "gpt-chat",
      "api_mode": "openai-completions",
      "extra_headers": {},
      "enabled_capabilities": []
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    class FakeChatCompletionsAPI:
        def create(self, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["model"] == "gpt-chat"
            assert kwargs["messages"] == [{"role": "user", "content": "你好"}]
            message = type("Message", (), {"content": "聊天完成", "tool_calls": []})()
            choice = type("Choice", (), {"message": message, "finish_reason": "stop"})()
            usage = type(
                "Usage",
                (),
                {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            )()
            return type(
                "Response",
                (),
                {
                    "id": "chatcmpl_001",
                    "_request_id": "req_chat_001",
                    "choices": [choice],
                    "usage": usage,
                },
            )()

    class FakeClient:
        def __init__(self) -> None:
            self.chat = type("Chat", (), {"completions": FakeChatCompletionsAPI()})()

    adapter = LLMAdapter(
        project_root=tmp_path,
        client_factory=lambda settings: FakeClient(),
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="llm",
    )

    result = adapter.respond(
        request=LLMRequest(
            messages=[LLMMessage(role="user", content="你好")],
            model_policy="quality",
        ),
        execution_context=execution_context,
    )

    assert result.content_blocks[0].content == "聊天完成"
    assert result.provider_trace is not None
    assert result.provider_trace.api_mode == "openai-completions"
    assert result.raw_response_meta["response_id"] == "chatcmpl_001"


def test_mcp_adapter_reads_server_from_pyproject_and_uses_client_factory(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
version = "0.0.1"

[mcp_servers.cunzhi]
type = "stdio"
command = "/tmp/cz.exe"
tool_timeout_sec = 60
""".strip(),
        encoding="utf-8",
    )

    class FakeMCPClient:
        def list_tools(self) -> list[dict[str, object]]:
            return [
                {
                    "server_name": "cunzhi",
                    "tool_name": "review",
                    "namespace": "cunzhi",
                    "transport": "stdio",
                }
            ]

        def call_tool(self, *, tool_name: str, arguments: dict[str, object]):
            assert tool_name == "review"
            assert arguments == {"prompt": "请审查"}
            return ToolExecutionResult(
                status="success",
                text="已提交",
                data={"accepted": True},
                execution_meta={"transport": "stdio"},
            )

    adapter = MCPAdapter(
        project_root=tmp_path,
        client_factory=lambda server: FakeMCPClient(),
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="mcp",
    )

    capabilities = adapter.list_capabilities(server_name="cunzhi")
    result = adapter.invoke(
        server_name="cunzhi",
        tool_name="review",
        arguments={"prompt": "请审查"},
        execution_context=execution_context,
    )

    assert capabilities == [
        {
            "server_name": "cunzhi",
            "tool_name": "review",
            "namespace": "cunzhi",
            "transport": "stdio",
        }
    ]
    assert result.status == "success"
    assert result.text == "已提交"
    assert result.data == {"accepted": True}
    assert result.execution_meta["server_name"] == "cunzhi"


def test_adapter_hub_preserves_llm_request_fields() -> None:
    captured: dict[str, object] = {}

    class RecordingLLMAdapter:
        def respond(self, *, request, execution_context):  # type: ignore[no-untyped-def]
            captured["request"] = request
            return LLMAdapter(responder=lambda _: "ok").respond(
                request=request,
                execution_context=execution_context,
            )

    hub = AdapterHub(llm=RecordingLLMAdapter())
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="llm",
    )

    result = hub.dispatch(
        action=NextAction(
            action_type="llm",
            action_target=None,
            action_input={
                "messages": [{"role": "user", "content": "你好"}],
                "model_policy": "fast",
                "profile_name": "default",
                "route_hint": "gpt-5.4",
                "tool_schemas": [{"name": "echo"}],
                "response_schema": {"type": "object"},
                "stream": True,
                "timeout": 1234,
            },
        ),
        execution_context=execution_context,
    )

    request = captured["request"]
    assert isinstance(request, LLMRequest)
    assert request.model_policy == "fast"
    assert request.profile_name == "default"
    assert request.route_hint == "gpt-5.4"
    assert request.tool_schemas == [{"name": "echo"}]
    assert request.response_schema == {"type": "object"}
    assert request.stream is True
    assert request.timeout == 1234
    assert result["source"] == "llm"


def test_llm_adapter_adds_default_user_agent_for_openai_client(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )
    (tmp_path / ".mz_agent").mkdir()
    (tmp_path / ".mz_agent" / "llm_profiles.json").write_text(
        """
{
  "connection": {
    "base_url": "https://example.com/v1",
    "api_key": "sk-test",
    "timeout": 60
  },
  "active_profile_name": "gpt-real",
  "profiles": [
    {
      "profile_name": "gpt-real",
      "display_name": "GPT Real",
      "model_name": "gpt-real",
      "extra_headers": {
        "X-Test-Header": "enabled"
      },
      "enabled_capabilities": []
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    captured_kwargs: dict[str, object] = {}

    class FakeResponsesAPI:
        def create(self, **kwargs):  # type: ignore[no-untyped-def]
            return type(
                "Response",
                (),
                {
                    "id": "resp_headers_001",
                    "_request_id": "req_headers_001",
                    "output_text": "PING_OK",
                    "output": [],
                    "usage": None,
                    "status": "completed",
                },
            )()

    class FakeOpenAI:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            captured_kwargs.update(kwargs)
            self.responses = FakeResponsesAPI()

    monkeypatch.setitem(
        sys.modules,
        "openai",
        types.SimpleNamespace(OpenAI=FakeOpenAI),
    )

    adapter = LLMAdapter(project_root=tmp_path, live_mode=True)
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="llm",
    )

    adapter.respond(
        request=LLMRequest(
            messages=[LLMMessage(role="user", content="你好")],
            model_policy="quality",
        ),
        execution_context=execution_context,
    )

    assert captured_kwargs["default_headers"] == {
        "User-Agent": DEFAULT_USER_AGENT,
        "X-Test-Header": "enabled",
    }
