from pydantic import ValidationError

from mz_agent.contracts.context import ContextSnapshot, ExecutionContext


def test_context_snapshot_uses_frozen_top_level_keys() -> None:
    snapshot = ContextSnapshot(current_plan=None)

    assert snapshot.model_dump() == {
        "perception": {},
        "stm": {},
        "current_plan": None,
        "skill_context": {},
        "last_observation": None,
    }


def test_execution_context_uses_frozen_tracking_fields() -> None:
    context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    assert context.model_dump() == {
        "request_id": "req_001",
        "session_id": "sess_001",
        "plan_id": None,
        "trace_id": "trace_001",
        "source": "react",
    }


def test_context_snapshot_rejects_extra_fields() -> None:
    try:
        ContextSnapshot.model_validate(
            {
                "current_plan": None,
                "unexpected": "bad",
            }
        )
    except ValidationError as exc:
        assert "unexpected" in str(exc)
    else:
        raise AssertionError("ContextSnapshot 未阻断额外字段。")


def test_execution_context_rejects_extra_fields() -> None:
    try:
        ExecutionContext.model_validate(
            {
                "request_id": "req_001",
                "session_id": "sess_001",
                "plan_id": None,
                "trace_id": "trace_001",
                "source": "react",
                "extra": "bad",
            }
        )
    except ValidationError as exc:
        assert "extra" in str(exc)
    else:
        raise AssertionError("ExecutionContext 未阻断额外字段。")

