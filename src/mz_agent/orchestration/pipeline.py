"""MzAgent 第一阶段主链单轮入口。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..adapters import AdapterHub
from ..contracts.action import AvailableAction, NextAction, ReActResult, build_react_result
from ..contracts.context import ContextSnapshot, ExecutionContext
from ..contracts.guardrails import GuardrailDecision
from ..contracts.state import GuardrailsDecisionKind, ReactStatus
from ..runtime.trace import bind_plan_context, inherit_execution_context
from ..runtime.writeback import WritebackRecord, prepare_writeback_record
from .guardrails import GuardrailsEvaluator, StaticGuardrailsEvaluator, evaluate_guardrails
from .planning import PlanningEngine, PlanningRequest
from .react import ReActEngine, ReActRequest
from .stm import InMemorySTM

ACTION_CHAIN_TYPES = {"skill", "tool", "mcp", "rag", "llm"}


class PipelineRoundResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    react_result: ReActResult
    output_text: str | None = None
    observation: dict[str, object] | None = None
    writeback_record: WritebackRecord | None = None
    context_snapshot: ContextSnapshot
    plan_created: bool = False
    guardrail_decisions: list[GuardrailDecision] = Field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        *,
        adapters: AdapterHub | None = None,
        planning_engine: PlanningEngine | None = None,
        react_engine: ReActEngine | None = None,
        guardrails_evaluator: GuardrailsEvaluator | None = None,
        stm: InMemorySTM | None = None,
    ) -> None:
        self._adapters = adapters or AdapterHub()
        self._planning_engine = planning_engine or PlanningEngine()
        self._react_engine = react_engine or ReActEngine()
        self._guardrails = guardrails_evaluator or StaticGuardrailsEvaluator()
        self._stm = stm or InMemorySTM()

    def run_round(
        self,
        *,
        goal: str,
        context_snapshot: ContextSnapshot,
        available_actions: list[AvailableAction],
        execution_context: ExecutionContext,
        max_steps: int = 5,
        planning_request: PlanningRequest | None = None,
    ) -> PipelineRoundResult:
        working_snapshot = context_snapshot
        plan_created = False
        self._stm.replace_context_snapshot(snapshot=working_snapshot)

        if planning_request is not None and context_snapshot.current_plan is None:
            plan = self._planning_engine.create_plan(request=planning_request)
            working_snapshot = context_snapshot.model_copy(
                update={"current_plan": self._planning_engine.create_plan_ref(plan=plan)}
            )
            self._stm.replace_context_snapshot(snapshot=working_snapshot)
            execution_context = bind_plan_context(
                context=execution_context,
                plan_id=plan.plan_id,
            )
            plan_created = True

        candidate = self._react_engine.decide(
            request=ReActRequest(
                goal=goal,
                context_snapshot=working_snapshot,
                available_actions=available_actions,
                max_steps=max_steps,
            )
        )

        if candidate.next_action is None:
            return PipelineRoundResult(
                react_result=candidate,
                context_snapshot=working_snapshot,
                plan_created=plan_created,
            )

        if candidate.next_action.action_type in ACTION_CHAIN_TYPES:
            return self._run_action_chain(
                candidate=candidate,
                context_snapshot=working_snapshot,
                execution_context=execution_context,
                plan_created=plan_created,
            )

        return self._run_answer_chain(
            candidate=candidate,
            context_snapshot=working_snapshot,
            execution_context=execution_context,
            plan_created=plan_created,
        )

    def _run_action_chain(
        self,
        *,
        candidate: ReActResult,
        context_snapshot: ContextSnapshot,
        execution_context: ExecutionContext,
        plan_created: bool,
    ) -> PipelineRoundResult:
        assert candidate.next_action is not None
        pre_decision = evaluate_guardrails(
            evaluator=self._guardrails,
            stage="pre_action",
            execution_context=execution_context,
            candidate_action=candidate.next_action,
        )

        if pre_decision.decision is not GuardrailsDecisionKind.ALLOW:
            mapped = self._map_pre_guardrail_result(
                decision=pre_decision.decision,
                candidate=candidate,
            )
            if mapped.next_action is not None and mapped.next_action.action_type == "clarify":
                return self._run_answer_chain(
                    candidate=mapped,
                    context_snapshot=context_snapshot,
                    execution_context=execution_context,
                    plan_created=plan_created,
                    prior_decisions=[pre_decision],
                )
            return PipelineRoundResult(
                react_result=mapped,
                context_snapshot=context_snapshot,
                plan_created=plan_created,
                guardrail_decisions=[pre_decision],
            )

        action_context = self._derive_action_context(
            execution_context=execution_context,
            action=candidate.next_action,
        )
        observation = self._adapters.dispatch(
            action=candidate.next_action,
            execution_context=action_context,
        )
        post_decision = evaluate_guardrails(
            evaluator=self._guardrails,
            stage="post_action",
            execution_context=execution_context,
            candidate_action=candidate.next_action,
            observation=observation,
        )

        final_result = (
            candidate
            if post_decision.decision is GuardrailsDecisionKind.ALLOW
            else self._map_pre_guardrail_result(
                decision=post_decision.decision,
                candidate=candidate,
            )
        )
        writeback_record = prepare_writeback_record(
            stage="post_action",
            execution_context=execution_context,
            react_status=final_result.react_status,
            current_step=self._current_step_for_writeback(
                react_result=final_result,
                context_snapshot=context_snapshot,
            ),
            observation=observation,
            metadata={"guardrails_decision": post_decision.decision.value},
        )
        updated_snapshot = self._stm.apply_writeback(record=writeback_record)
        return PipelineRoundResult(
            react_result=final_result,
            observation=observation,
            writeback_record=writeback_record,
            context_snapshot=updated_snapshot,
            plan_created=plan_created,
            guardrail_decisions=[pre_decision, post_decision],
        )

    def _run_answer_chain(
        self,
        *,
        candidate: ReActResult,
        context_snapshot: ContextSnapshot,
        execution_context: ExecutionContext,
        plan_created: bool,
        prior_decisions: list[GuardrailDecision] | None = None,
    ) -> PipelineRoundResult:
        assert candidate.next_action is not None
        output_text = self._resolve_output_text(action=candidate.next_action)
        pre_decision = evaluate_guardrails(
            evaluator=self._guardrails,
            stage="pre_answer",
            execution_context=execution_context,
            candidate_action=candidate.next_action,
            candidate_answer=output_text,
        )

        if pre_decision.decision is GuardrailsDecisionKind.BLOCK:
            return PipelineRoundResult(
                react_result=build_react_result(react_status=ReactStatus.BLOCKED),
                context_snapshot=context_snapshot,
                plan_created=plan_created,
                guardrail_decisions=[*(prior_decisions or []), pre_decision],
            )

        if pre_decision.decision is GuardrailsDecisionKind.DEGRADE:
            return PipelineRoundResult(
                react_result=build_react_result(react_status=ReactStatus.DEGRADED),
                context_snapshot=context_snapshot,
                plan_created=plan_created,
                guardrail_decisions=[*(prior_decisions or []), pre_decision],
            )

        if pre_decision.decision is GuardrailsDecisionKind.CLARIFY:
            candidate = build_react_result(
                react_status=ReactStatus.RUNNING,
                next_action=NextAction(
                    action_type="clarify",
                    action_target=None,
                    action_input={"message": "请补充必要信息。"},
                ),
            )
            output_text = "请补充必要信息。"

        if candidate.next_action.action_type == "finish":
            final_result = build_react_result(
                react_status=ReactStatus.FINISHED,
                final_answer=output_text,
            )
        else:
            final_result = candidate

        post_decision = evaluate_guardrails(
            evaluator=self._guardrails,
            stage="post_answer",
            execution_context=execution_context,
            candidate_action=candidate.next_action,
            candidate_answer=output_text,
        )

        writeback_record = prepare_writeback_record(
            stage="post_answer",
            execution_context=execution_context,
            react_status=final_result.react_status,
            current_step=self._current_step_for_writeback(
                react_result=final_result,
                context_snapshot=context_snapshot,
            ),
            observation={
                "source": "answer",
                "output_text": output_text,
                "action_type": candidate.next_action.action_type,
            },
            final_answer=output_text if final_result.react_status is ReactStatus.FINISHED else None,
            metadata={"guardrails_decision": post_decision.decision.value},
        )
        updated_snapshot = self._stm.apply_writeback(record=writeback_record)
        return PipelineRoundResult(
            react_result=final_result,
            output_text=output_text,
            observation=writeback_record.observation,
            writeback_record=writeback_record,
            context_snapshot=updated_snapshot,
            plan_created=plan_created,
            guardrail_decisions=[*(prior_decisions or []), pre_decision, post_decision],
        )

    @staticmethod
    def _map_pre_guardrail_result(
        *,
        decision: GuardrailsDecisionKind,
        candidate: ReActResult,
    ) -> ReActResult:
        if decision is GuardrailsDecisionKind.BLOCK:
            return build_react_result(react_status=ReactStatus.BLOCKED)
        if decision is GuardrailsDecisionKind.DEGRADE:
            return build_react_result(react_status=ReactStatus.DEGRADED)
        if decision is GuardrailsDecisionKind.CLARIFY:
            return build_react_result(
                react_status=ReactStatus.RUNNING,
                next_action=NextAction(
                    action_type="clarify",
                    action_target=None,
                    action_input={"message": "请补充必要信息。"},
                ),
            )
        return candidate

    @staticmethod
    def _resolve_output_text(*, action: NextAction) -> str:
        if action.action_type == "finish":
            answer = action.action_input.get("answer")
            if isinstance(answer, str) and answer:
                return answer
            return "任务已完成。"
        message = action.action_input.get("message")
        if isinstance(message, str) and message:
            return message
        return "请补充必要信息。"

    @staticmethod
    def _current_step_for_writeback(
        *,
        react_result: ReActResult,
        context_snapshot: ContextSnapshot,
    ):
        if react_result.react_status is ReactStatus.FINISHED:
            return None
        current_plan = context_snapshot.current_plan
        return None if current_plan is None else current_plan.current_step

    @staticmethod
    def _derive_action_context(
        *,
        execution_context: ExecutionContext,
        action: NextAction,
    ) -> ExecutionContext:
        if action.action_type == "tool":
            return inherit_execution_context(parent=execution_context, source="tool")
        if action.action_type == "mcp":
            return inherit_execution_context(parent=execution_context, source="mcp")
        if action.action_type == "llm":
            return inherit_execution_context(parent=execution_context, source="llm")
        return execution_context
