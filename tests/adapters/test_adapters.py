from mz_agent.adapters.llm import LLMAdapter
from mz_agent.adapters.mcp import MCPAdapter
from mz_agent.adapters.tool import ToolAdapter
from mz_agent.contracts.context import ExecutionContext
from mz_agent.contracts.llm import LLMMessage, LLMRequest
from mz_agent.contracts.tooling import (
    MCPBinding,
    ToolCallerContext,
    ToolDefinition,
    ToolExecutionPolicy,
    ToolExecutionRequest,
)


def test_tool_adapter_normalizes_handler_result() -> None:
    adapter = ToolAdapter()
    adapter.register(
        definition=ToolDefinition(
            name="echo",
            description="回显工具",
            input_schema={"type": "object", "required": ["query"]},
            permission_domain="general",
            risk_level="low",
            idempotent=True,
            requires_confirmation=False,
            handler=lambda query: {"text": f"收到：{query}", "data": {"query": query}},
        )
    )

    result = adapter.execute(
        request=ToolExecutionRequest(
            request_id="req_001",
            session_id="sess_001",
            tool_name="echo",
            arguments={"query": "hello"},
            execution_policy=ToolExecutionPolicy(idempotent=True),
            caller_context=ToolCallerContext(source="react", trace_id="trace_001"),
        )
    )

    assert result.model_dump(mode="json") == {
        "status": "success",
        "text": "收到：hello",
        "data": {"query": "hello"},
        "error_code": None,
        "message": None,
        "result_schema_version": "v1",
        "execution_meta": {},
    }


def test_mcp_adapter_lists_capabilities_and_invokes_handler() -> None:
    adapter = MCPAdapter()
    adapter.register(
        binding=MCPBinding(
            server_name="docs",
            transport="stdio",
            tool_name="search",
            namespace="docs",
        ),
        handler=lambda query: {"text": f"命中：{query}", "data": {"query": query}},
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="mcp",
    )

    capabilities = adapter.list_capabilities(server_name="docs")
    result = adapter.invoke(
        server_name="docs",
        tool_name="search",
        arguments={"query": "协议"},
        execution_context=execution_context,
    )

    assert capabilities == [
        {
            "server_name": "docs",
            "tool_name": "search",
            "namespace": "docs",
            "transport": "stdio",
        }
    ]
    assert result.text == "命中：协议"

def test_llm_adapter_returns_normalized_payload() -> None:
    llm_adapter = LLMAdapter()
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="llm",
    )

    llm_result = llm_adapter.respond(
        request=LLMRequest(
            messages=[LLMMessage(role="user", content="你好")],
            model_policy="quality",
            route_hint="openai-mini",
        ),
        execution_context=execution_context,
    )

    assert llm_result.provider_trace is not None
    assert llm_result.provider_trace.provider in {"openai_native", "openai_compatible_proxy"}
