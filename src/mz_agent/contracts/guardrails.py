"""MzAgent 第一阶段 Guardrails 协议。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .action import NextAction, ReActResult, build_react_result
from .state import GuardrailsDecisionKind, ReactStatus
from ..runtime.errors import DomainValidationError

GuardrailStage = Literal["pre_action", "post_action", "pre_answer", "post_answer"]


class GuardrailDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: GuardrailStage
    decision: GuardrailsDecisionKind


class RiskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: GuardrailStage
    event_type: str


def map_guardrail_decision(
    *,
    decision: GuardrailsDecisionKind,
    candidate_action: NextAction | None = None,
    candidate_answer: str | None = None,
) -> ReActResult:
    if decision is GuardrailsDecisionKind.ALLOW:
        if (candidate_action is None) == (candidate_answer is None):
            raise DomainValidationError("放行决策必须且只能携带一种候选结果。")
        if candidate_action is not None:
            return build_react_result(
                react_status=ReactStatus.RUNNING,
                next_action=candidate_action,
            )
        return build_react_result(
            react_status=ReactStatus.FINISHED,
            final_answer=candidate_answer,
        )

    if candidate_action is not None or candidate_answer is not None:
        raise DomainValidationError("非放行决策不得继续保留原候选结果。")

    if decision is GuardrailsDecisionKind.BLOCK:
        return build_react_result(react_status=ReactStatus.BLOCKED)
    if decision is GuardrailsDecisionKind.DEGRADE:
        return build_react_result(react_status=ReactStatus.DEGRADED)
    if decision is GuardrailsDecisionKind.CLARIFY:
        clarify_action = NextAction(
            action_type="clarify",
            action_target=None,
            action_input={},
        )
        return build_react_result(
            react_status=ReactStatus.RUNNING,
            next_action=clarify_action,
        )

    raise DomainValidationError("收到未支持的 Guardrails 决策值。")

