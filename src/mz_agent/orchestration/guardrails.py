"""MzAgent 第一阶段 Guardrails 编排壳。"""

from __future__ import annotations

from typing import Protocol

from ..contracts.action import NextAction
from ..contracts.context import ExecutionContext
from ..contracts.guardrails import GuardrailDecision, GuardrailStage
from ..contracts.state import GuardrailsDecisionKind

DynamicObject = dict[str, object]


class GuardrailsEvaluator(Protocol):
    def evaluate(
        self,
        *,
        stage: GuardrailStage,
        execution_context: ExecutionContext,
        candidate_action: NextAction | None = None,
        candidate_answer: str | None = None,
        observation: DynamicObject | None = None,
    ) -> GuardrailsDecisionKind:
        ...


class StaticGuardrailsEvaluator:
    def __init__(
        self,
        *,
        stage_decisions: dict[GuardrailStage, GuardrailsDecisionKind] | None = None,
    ) -> None:
        self._stage_decisions = stage_decisions or {}

    def evaluate(
        self,
        *,
        stage: GuardrailStage,
        execution_context: ExecutionContext,
        candidate_action: NextAction | None = None,
        candidate_answer: str | None = None,
        observation: DynamicObject | None = None,
    ) -> GuardrailsDecisionKind:
        return self._stage_decisions.get(stage, GuardrailsDecisionKind.ALLOW)


def evaluate_guardrails(
    *,
    evaluator: GuardrailsEvaluator,
    stage: GuardrailStage,
    execution_context: ExecutionContext,
    candidate_action: NextAction | None = None,
    candidate_answer: str | None = None,
    observation: DynamicObject | None = None,
) -> GuardrailDecision:
    return GuardrailDecision(
        stage=stage,
        decision=evaluator.evaluate(
            stage=stage,
            execution_context=execution_context,
            candidate_action=candidate_action,
            candidate_answer=candidate_answer,
            observation=observation,
        ),
    )

