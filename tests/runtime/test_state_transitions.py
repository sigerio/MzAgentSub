from mz_agent.contracts.planning import CurrentStep
from mz_agent.contracts.state import CursorState, ReactStatus, StepState
from mz_agent.runtime.errors import DomainValidationError, TransitionViolationError
from mz_agent.runtime.transitions import (
    invalidate_current_step_on_plan_change,
    validate_cursor_transition,
    validate_react_transition,
    validate_step_transition,
)


def test_step_state_values_are_frozen() -> None:
    assert [state.value for state in StepState] == [
        "todo",
        "in_progress",
        "done",
        "abandoned",
    ]


def test_cursor_transition_allows_only_frozen_paths() -> None:
    assert (
        validate_cursor_transition(
            current=CursorState.PENDING,
            target=CursorState.ACTIVE,
        )
        is CursorState.ACTIVE
    )

    try:
        validate_cursor_transition(
            current=CursorState.PENDING,
            target=CursorState.COMPLETED,
        )
    except TransitionViolationError as exc:
        assert "pending -> completed" in str(exc)
    else:
        raise AssertionError("非法的 cursor_state 转换没有被阻断。")


def test_step_transition_allows_only_frozen_paths() -> None:
    assert (
        validate_step_transition(
            current=StepState.TODO,
            target=StepState.IN_PROGRESS,
        )
        is StepState.IN_PROGRESS
    )

    try:
        validate_step_transition(
            current=StepState.TODO,
            target=StepState.DONE,
        )
    except TransitionViolationError as exc:
        assert "todo -> done" in str(exc)
    else:
        raise AssertionError("非法的 step_state 转换没有被阻断。")


def test_react_transition_rejects_terminal_backflow() -> None:
    assert (
        validate_react_transition(
            current=ReactStatus.RUNNING,
            target=ReactStatus.DEGRADED,
        )
        is ReactStatus.DEGRADED
    )

    try:
        validate_react_transition(
            current=ReactStatus.FINISHED,
            target=ReactStatus.BLOCKED,
        )
    except TransitionViolationError as exc:
        assert "finished -> blocked" in str(exc)
    else:
        raise AssertionError("终止态回流没有被阻断。")


def test_react_transition_rejects_non_enum_target() -> None:
    try:
        validate_react_transition(
            current=ReactStatus.RUNNING,
            target="clarify",  # type: ignore[arg-type]
        )
    except DomainValidationError as exc:
        assert "ReactStatus 枚举值" in str(exc)
    else:
        raise AssertionError("clarify 不应被当作 react_status 主状态。")


def test_plan_version_change_invalidates_current_step() -> None:
    current_step = CurrentStep(
        step_id="step_01",
        cursor_state=CursorState.ACTIVE,
    )

    assert (
        invalidate_current_step_on_plan_change(
            previous_plan_version=1,
            current_plan_version=1,
            current_step=current_step,
        )
        is current_step
    )
    assert (
        invalidate_current_step_on_plan_change(
            previous_plan_version=1,
            current_plan_version=2,
            current_step=current_step,
        )
        is None
    )
