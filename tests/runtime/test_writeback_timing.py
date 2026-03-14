from mz_agent.contracts.context import ContextSnapshot, ExecutionContext
from mz_agent.contracts.planning import CurrentPlanRef, CurrentStep
from mz_agent.contracts.state import CursorState, ReactStatus, StepState
from mz_agent.orchestration.stm import InMemorySTM
from mz_agent.runtime.errors import DomainValidationError
from mz_agent.runtime.writeback import prepare_writeback_record


def test_writeback_only_allows_post_stages() -> None:
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    try:
        prepare_writeback_record(
            stage="pre_action",
            execution_context=execution_context,
            react_status=ReactStatus.RUNNING,
            current_step=None,
        )
    except DomainValidationError as exc:
        assert "post_action" in str(exc)
    else:
        raise AssertionError("回写门禁未阻断 pre_action。")


def test_finished_writeback_clears_current_step_in_stm() -> None:
    snapshot = ContextSnapshot(
        current_plan=CurrentPlanRef(
            plan_id="plan_001",
            plan_version=1,
            current_step=CurrentStep(step_id="step_01", cursor_state=CursorState.ACTIVE),
            step_state={"step_01": StepState.DONE},
        )
    )
    stm = InMemorySTM(initial_snapshot=snapshot)
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id="plan_001",
        trace_id="trace_001",
        source="react",
    )

    record = prepare_writeback_record(
        stage="post_answer",
        execution_context=execution_context,
        react_status=ReactStatus.FINISHED,
        current_step=None,
        final_answer="已完成",
    )
    updated_snapshot = stm.apply_writeback(record=record)

    assert updated_snapshot.current_plan is not None
    assert updated_snapshot.current_plan.current_step is None
    assert updated_snapshot.last_observation == {
        "source": "answer",
        "output_text": "已完成",
    }
