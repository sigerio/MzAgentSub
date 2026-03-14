"""MzAgent 第一阶段追踪继承门禁。"""

from __future__ import annotations

from typing import Final

from ..contracts.context import ExecutionContext, ExecutionSource
from .errors import DomainValidationError

_UNCHANGED: Final = object()


def inherit_execution_context(
    *,
    parent: ExecutionContext,
    source: ExecutionSource,
    plan_id: str | None | object = _UNCHANGED,
    trace_suffix: str | None = None,
) -> ExecutionContext:
    next_plan_id = parent.plan_id if plan_id is _UNCHANGED else plan_id
    next_trace_id = f"{parent.trace_id}.{trace_suffix or source}"
    return ExecutionContext(
        request_id=parent.request_id,
        session_id=parent.session_id,
        plan_id=next_plan_id,
        trace_id=next_trace_id,
        source=source,
    )


def bind_plan_context(
    *,
    context: ExecutionContext,
    plan_id: str,
) -> ExecutionContext:
    return ExecutionContext(
        request_id=context.request_id,
        session_id=context.session_id,
        plan_id=plan_id,
        trace_id=f"{context.trace_id}.planning",
        source="planning",
    )


def assert_inherited_context(
    *,
    parent: ExecutionContext,
    child: ExecutionContext,
    allow_new_plan_id: bool = False,
) -> None:
    if child.request_id != parent.request_id:
        raise DomainValidationError("子执行上下文不得重生 request_id。")
    if child.session_id != parent.session_id:
        raise DomainValidationError("子执行上下文不得重生 session_id。")
    if not allow_new_plan_id and child.plan_id != parent.plan_id:
        raise DomainValidationError("未显式授权时不得改写 plan_id。")

