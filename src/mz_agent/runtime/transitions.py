"""MzAgent 第一阶段状态门禁纯函数。"""

from __future__ import annotations

from ..contracts.planning import CurrentStep
from ..contracts.state import CursorState, ReactStatus, StepState
from .errors import DomainValidationError, TransitionViolationError

STEP_TRANSITIONS: dict[StepState, set[StepState]] = {
    StepState.TODO: {StepState.IN_PROGRESS, StepState.ABANDONED},
    StepState.IN_PROGRESS: {StepState.DONE, StepState.ABANDONED},
    StepState.DONE: set(),
    StepState.ABANDONED: set(),
}

CURSOR_TRANSITIONS: dict[CursorState, set[CursorState]] = {
    CursorState.PENDING: {CursorState.ACTIVE, CursorState.ABANDONED},
    CursorState.ACTIVE: {CursorState.COMPLETED, CursorState.ABANDONED},
    CursorState.COMPLETED: set(),
    CursorState.ABANDONED: set(),
}

REACT_TRANSITIONS: dict[ReactStatus, set[ReactStatus]] = {
    ReactStatus.RUNNING: {
        ReactStatus.RUNNING,
        ReactStatus.FINISHED,
        ReactStatus.BLOCKED,
        ReactStatus.DEGRADED,
    },
    ReactStatus.FINISHED: set(),
    ReactStatus.BLOCKED: set(),
    ReactStatus.DEGRADED: set(),
}


def validate_step_transition(*, current: StepState, target: StepState) -> StepState:
    _ensure_step_state(current=current, target=target)
    if target not in STEP_TRANSITIONS[current]:
        raise TransitionViolationError(
            f"不允许的 step_state 转换: {current.value} -> {target.value}"
        )
    return target


def validate_cursor_transition(
    *, current: CursorState, target: CursorState
) -> CursorState:
    _ensure_cursor_state(current=current, target=target)
    if target not in CURSOR_TRANSITIONS[current]:
        raise TransitionViolationError(
            f"不允许的 cursor_state 转换: {current.value} -> {target.value}"
        )
    return target


def validate_react_transition(
    *, current: ReactStatus, target: ReactStatus
) -> ReactStatus:
    _ensure_react_status(current=current, target=target)
    if target not in REACT_TRANSITIONS[current]:
        raise TransitionViolationError(
            f"不允许的 react_status 转换: {current.value} -> {target.value}"
        )
    return target


def invalidate_current_step_on_plan_change(
    *,
    previous_plan_version: int | str,
    current_plan_version: int | str,
    current_step: CurrentStep | None,
) -> CurrentStep | None:
    if previous_plan_version == current_plan_version:
        return current_step
    return None


def _ensure_step_state(*, current: object, target: object) -> None:
    if not isinstance(current, StepState) or not isinstance(target, StepState):
        raise DomainValidationError("step_state 门禁函数只接受 StepState 枚举值。")


def _ensure_cursor_state(*, current: object, target: object) -> None:
    if not isinstance(current, CursorState) or not isinstance(target, CursorState):
        raise DomainValidationError("cursor_state 门禁函数只接受 CursorState 枚举值。")


def _ensure_react_status(*, current: object, target: object) -> None:
    if not isinstance(current, ReactStatus) or not isinstance(target, ReactStatus):
        raise DomainValidationError("react_status 门禁函数只接受 ReactStatus 枚举值。")

