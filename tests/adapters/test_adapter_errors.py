from mz_agent.adapters.llm import LLMAdapter
from mz_agent.adapters.mcp import MCPAdapter
from mz_agent.adapters.tool import ToolAdapter
from mz_agent.contracts.context import ExecutionContext
from mz_agent.contracts.llm import LLMRequest
from mz_agent.contracts.tooling import (
    MCPBinding,
    ToolCallerContext,
    ToolDefinition,
    ToolExecutionPolicy,
    ToolExecutionRequest,
)


def test_tool_adapter_handles_missing_definition_and_dry_run() -> None:
    adapter = ToolAdapter()

    missing = adapter.execute(
        request=ToolExecutionRequest(
            request_id="req_001",
            session_id="sess_001",
            tool_name="missing",
            execution_policy=ToolExecutionPolicy(),
            caller_context=ToolCallerContext(source="react", trace_id="trace_001"),
        )
    )
    assert missing.error_code == "TOL_001"

    adapter.register(
        definition=ToolDefinition(
            name="echo",
            description="回显工具",
            input_schema={"type": "object", "required": ["query"]},
            permission_domain="general",
            risk_level="low",
            idempotent=True,
            requires_confirmation=False,
            handler=lambda query: query,
        )
    )
    dry_run = adapter.execute(
        request=ToolExecutionRequest(
            request_id="req_001",
            session_id="sess_001",
            tool_name="echo",
            arguments={"query": "hello"},
            execution_policy=ToolExecutionPolicy(dry_run=True),
            caller_context=ToolCallerContext(source="react", trace_id="trace_001"),
        )
    )
    assert dry_run.execution_meta == {"dry_run": True}
def test_mcp_and_llm_error_paths_are_stable() -> None:
    mcp = MCPAdapter()
    mcp.register(
        binding=MCPBinding(
            server_name="docs",
            transport="stdio",
            tool_name="search",
            namespace="docs",
            enabled=False,
        ),
        handler=lambda query: query,
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )
    mcp_result = mcp.invoke(
        server_name="docs",
        tool_name="search",
        arguments={"query": "协议"},
        execution_context=execution_context,
    )
    assert mcp_result.error_code == "MCP_001"

    llm = LLMAdapter(responder=lambda request: "直接返回")
    llm_result = llm.respond(
        request=LLMRequest(messages=[], model_policy="quality"),
        execution_context=execution_context,
    )
    assert llm_result.content_blocks[0].content == "直接返回"
