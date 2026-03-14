from mz_agent.contracts.context import ExecutionContext
from mz_agent.runtime.errors import DomainValidationError
from mz_agent.runtime.trace import (
    assert_inherited_context,
    bind_plan_context,
    inherit_execution_context,
)


def test_inherit_execution_context_keeps_request_and_session() -> None:
    parent = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id="plan_001",
        trace_id="trace_001",
        source="react",
    )

    child = inherit_execution_context(parent=parent, source="tool")

    assert child.model_dump() == {
        "request_id": "req_001",
        "session_id": "sess_001",
        "plan_id": "plan_001",
        "trace_id": "trace_001.tool",
        "source": "tool",
    }


def test_bind_plan_context_only_rebinds_plan_slot() -> None:
    context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    rebound = bind_plan_context(context=context, plan_id="plan_002")

    assert rebound.model_dump() == {
        "request_id": "req_001",
        "session_id": "sess_001",
        "plan_id": "plan_002",
        "trace_id": "trace_001.planning",
        "source": "planning",
    }


def test_assert_inherited_context_rejects_regenerated_request_id() -> None:
    parent = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id="plan_001",
        trace_id="trace_001",
        source="react",
    )
    child = ExecutionContext(
        request_id="req_002",
        session_id="sess_001",
        plan_id="plan_001",
        trace_id="trace_001.tool",
        source="tool",
    )

    try:
        assert_inherited_context(parent=parent, child=child)
    except DomainValidationError as exc:
        assert "request_id" in str(exc)
    else:
        raise AssertionError("继承校验未阻断 request_id 重生。")
