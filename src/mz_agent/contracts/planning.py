"""MzAgent 第一阶段计划协议。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .state import CursorState, StepState


class CurrentStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    cursor_state: CursorState


class CurrentPlanRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    plan_version: int = Field(ge=1)
    current_step: CurrentStep | None
    step_state: dict[str, StepState]


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    goal: str
    depends_on: list[str] = Field(default_factory=list)
    done_when: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    plan_version: int = Field(ge=1)
    steps: list[PlanStep]
    step_state: dict[str, StepState]

