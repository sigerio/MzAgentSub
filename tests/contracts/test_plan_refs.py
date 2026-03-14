from pydantic import ValidationError

from mz_agent.contracts.planning import CurrentPlanRef, CurrentStep, Plan, PlanStep


def test_plan_and_plan_step_keep_frozen_structure() -> None:
    plan = Plan.model_validate(
        {
            "plan_id": "plan_001",
            "plan_version": 1,
            "steps": [
                {
                    "step_id": "step_01",
                    "goal": "收集输入",
                    "depends_on": [],
                    "done_when": ["输入已确认"],
                }
            ],
            "step_state": {
                "step_01": "todo",
            },
        }
    )

    assert plan.model_dump(mode="json") == {
        "plan_id": "plan_001",
        "plan_version": 1,
        "steps": [
            {
                "step_id": "step_01",
                "goal": "收集输入",
                "depends_on": [],
                "done_when": ["输入已确认"],
            }
        ],
        "step_state": {
            "step_01": "todo",
        },
    }


def test_current_plan_ref_keeps_current_step_binding() -> None:
    current_plan = CurrentPlanRef(
        plan_id="plan_001",
        plan_version=1,
        current_step=CurrentStep(step_id="step_02", cursor_state="active"),
        step_state={"step_01": "done", "step_02": "in_progress"},
    )

    assert current_plan.current_step is not None
    assert current_plan.current_step.step_id == "step_02"
    assert current_plan.current_step.cursor_state.value == "active"


def test_current_plan_ref_rejects_extra_fields() -> None:
    try:
        CurrentPlanRef.model_validate(
            {
                "plan_id": "plan_001",
                "plan_version": 1,
                "current_step": None,
                "step_state": {},
                "extra": True,
            }
        )
    except ValidationError as exc:
        assert "extra" in str(exc)
    else:
        raise AssertionError("CurrentPlanRef 未阻断额外字段。")


def test_plan_step_rejects_extra_fields() -> None:
    try:
        PlanStep.model_validate(
            {
                "step_id": "step_01",
                "goal": "收集输入",
                "depends_on": [],
                "done_when": [],
                "extra": True,
            }
        )
    except ValidationError as exc:
        assert "extra" in str(exc)
    else:
        raise AssertionError("PlanStep 未阻断额外字段。")
