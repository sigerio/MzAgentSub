from mz_agent.contracts.action import AvailableAction
from mz_agent.contracts.context import ContextSnapshot, ExecutionContext
from mz_agent.contracts.state import GuardrailsDecisionKind, ReactStatus
from mz_agent.orchestration.guardrails import StaticGuardrailsEvaluator
from mz_agent.orchestration.pipeline import Pipeline
from mz_agent.orchestration.planning import PlanningEngine, PlanningRequest
from mz_agent.orchestration.react import ReActEngine, ReActRequest


def test_planning_engine_increments_plan_version() -> None:
    engine = PlanningEngine()
    request = PlanningRequest(
        objective="完成目标",
        current_state={"step_goals": ["第一步", "第二步"]},
    )

    first = engine.create_plan(request=request)
    second = engine.create_plan(request=request, previous_plan=first)

    assert first.plan_id == second.plan_id
    assert first.plan_version == 1
    assert second.plan_version == 2
    assert second.steps[1].depends_on == ["step_01"]


def test_react_engine_prefers_skill_before_other_actions() -> None:
    engine = ReActEngine()
    result = engine.decide(
        request=ReActRequest(
            goal="完成写作",
            context_snapshot=ContextSnapshot(
                current_plan=None,
                skill_context={"selected_skill": "writer"},
            ),
            available_actions=[
                AvailableAction(
                    action_type="tool",
                    targets=["search_docs"],
                    availability="available",
                ),
                AvailableAction(
                    action_type="skill",
                    targets=["writer"],
                    availability="available",
                ),
            ],
        )
    )

    assert result.react_status is ReactStatus.RUNNING
    assert result.next_action is not None
    assert result.next_action.action_type == "skill"
    assert result.next_action.action_target == "writer"


def test_pipeline_pre_action_clarify_switches_to_answer_chain() -> None:
    pipeline = Pipeline(
        guardrails_evaluator=StaticGuardrailsEvaluator(
            stage_decisions={"pre_action": GuardrailsDecisionKind.CLARIFY}
        )
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    result = pipeline.run_round(
        goal="继续任务",
        context_snapshot=ContextSnapshot(current_plan=None),
        available_actions=[
            AvailableAction(
                action_type="tool",
                targets=["search_docs"],
                availability="available",
            )
        ],
        execution_context=execution_context,
    )

    assert result.react_result.react_status is ReactStatus.RUNNING
    assert result.output_text == "请补充必要信息。"
    assert result.writeback_record is not None
    assert result.writeback_record.stage == "post_answer"

