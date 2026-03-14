"""MzAgent 第一阶段 Planning 编排壳。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.planning import CurrentPlanRef, Plan, PlanStep
from ..contracts.state import StepState

DynamicObject = dict[str, object]


class PlanningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    constraints: list[str] = Field(default_factory=list)
    current_state: DynamicObject = Field(default_factory=dict)


class PlanningEngine:
    def __init__(self) -> None:
        self._plan_counter = 0

    def create_plan(
        self,
        *,
        request: PlanningRequest,
        previous_plan: Plan | None = None,
    ) -> Plan:
        plan_version = 1 if previous_plan is None else previous_plan.plan_version + 1
        if previous_plan is not None:
            plan_id = previous_plan.plan_id
        else:
            self._plan_counter += 1
            plan_id = f"plan_{self._plan_counter:04d}"
        raw_step_goals = request.current_state.get("step_goals")
        step_goals = (
            [str(item) for item in raw_step_goals]
            if isinstance(raw_step_goals, list) and raw_step_goals
            else [request.objective]
        )

        steps: list[PlanStep] = []
        for index, goal in enumerate(step_goals, start=1):
            step_id = f"step_{index:02d}"
            depends_on = [] if index == 1 else [f"step_{index - 1:02d}"]
            steps.append(
                PlanStep(
                    step_id=step_id,
                    goal=goal,
                    depends_on=depends_on,
                    done_when=[f"完成：{goal}"],
                )
            )

        return Plan(
            plan_id=plan_id,
            plan_version=plan_version,
            steps=steps,
            step_state={step.step_id: StepState.TODO for step in steps},
        )

    def create_plan_ref(self, *, plan: Plan) -> CurrentPlanRef:
        return CurrentPlanRef(
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            current_step=None,
            step_state=plan.step_state,
        )
