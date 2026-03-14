from mz_agent.contracts.tooling import (
    ToolCallerContext,
    ToolDefinition,
    ToolExecutionPolicy,
    ToolExecutionRequest,
    ToolExecutionResult,
)


def test_tool_definition_keeps_required_fields() -> None:
    definition = ToolDefinition(
        name="echo",
        description="回显工具",
        input_schema={"type": "object", "required": ["query"]},
        permission_domain="general",
        risk_level="low",
        idempotent=True,
        requires_confirmation=False,
        handler=lambda query: query,
    )

    assert definition.name == "echo"
    assert definition.risk_level == "low"
    assert definition.result_schema_version == "v1"


def test_tool_execution_policy_defaults_are_stable() -> None:
    policy = ToolExecutionPolicy()

    assert policy.model_dump(mode="json") == {
        "timeout_ms": 30000,
        "retry_limit": 0,
        "idempotent": False,
        "dry_run": False,
    }


def test_tool_request_and_result_dump_are_stable() -> None:
    request = ToolExecutionRequest(
        request_id="req_001",
        session_id="sess_001",
        tool_name="echo",
        arguments={"query": "hello"},
        execution_policy=ToolExecutionPolicy(idempotent=True),
        caller_context=ToolCallerContext(source="react", trace_id="trace_001"),
    )
    result = ToolExecutionResult(
        status="success",
        text="ok",
        data={"query": "hello"},
    )

    assert request.model_dump(mode="json") == {
        "request_id": "req_001",
        "session_id": "sess_001",
        "tool_name": "echo",
        "arguments": {"query": "hello"},
        "execution_policy": {
            "timeout_ms": 30000,
            "retry_limit": 0,
            "idempotent": True,
            "dry_run": False,
        },
        "caller_context": {
            "source": "react",
            "user_id": None,
            "trace_id": "trace_001",
            "plan_step_id": None,
        },
    }
    assert result.model_dump(mode="json") == {
        "status": "success",
        "text": "ok",
        "data": {"query": "hello"},
        "error_code": None,
        "message": None,
        "result_schema_version": "v1",
        "execution_meta": {},
    }

