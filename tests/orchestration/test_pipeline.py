from mz_agent.adapters import AdapterHub, ToolAdapter
from mz_agent.contracts.action import AvailableAction
from mz_agent.contracts.context import ContextSnapshot, ExecutionContext
from mz_agent.contracts.planning import CurrentPlanRef, CurrentStep
from mz_agent.contracts.state import CursorState, ReactStatus, StepState
from mz_agent.contracts.tooling import ToolDefinition
from mz_agent.orchestration import Pipeline


def test_pipeline_runs_action_chain_and_writes_back_after_post_action() -> None:
    tool_adapter = ToolAdapter()
    tool_adapter.register(
        definition=ToolDefinition(
            name="search_docs",
            description="搜索文档",
            input_schema={"type": "object", "required": []},
            permission_domain="docs",
            risk_level="low",
            idempotent=True,
            requires_confirmation=False,
            handler=lambda: {"text": "已执行搜索", "data": {"hits": 1}},
        )
    )
    pipeline = Pipeline(adapters=AdapterHub(tool=tool_adapter))
    snapshot = ContextSnapshot(current_plan=None)
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    result = pipeline.run_round(
        goal="搜索文档",
        context_snapshot=snapshot,
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
    assert result.writeback_record is not None
    assert result.writeback_record.stage == "post_action"
    assert result.context_snapshot.last_observation == {
        "source": "tool",
        "result": {
            "status": "success",
            "text": "已执行搜索",
            "data": {"hits": 1},
            "error_code": None,
            "message": None,
            "result_schema_version": "v1",
            "execution_meta": {},
        },
    }


def test_pipeline_runs_answer_chain_and_clears_current_step_on_finish() -> None:
    pipeline = Pipeline()
    snapshot = ContextSnapshot(
        current_plan=CurrentPlanRef(
            plan_id="plan_001",
            plan_version=1,
            current_step=CurrentStep(step_id="step_01", cursor_state=CursorState.ACTIVE),
            step_state={"step_01": StepState.DONE},
        ),
        last_observation={"draft_answer": "整理完成"},
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id="plan_001",
        trace_id="trace_001",
        source="react",
    )

    result = pipeline.run_round(
        goal="整理结果",
        context_snapshot=snapshot,
        available_actions=[
            AvailableAction(
                action_type="finish",
                targets=[],
                availability="available",
            )
        ],
        execution_context=execution_context,
    )

    assert result.react_result.react_status is ReactStatus.FINISHED
    assert result.output_text == "整理完成"
    assert result.writeback_record is not None
    assert result.writeback_record.stage == "post_answer"
    assert result.context_snapshot.current_plan is not None
    assert result.context_snapshot.current_plan.current_step is None

