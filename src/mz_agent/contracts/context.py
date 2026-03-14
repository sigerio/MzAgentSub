"""MzAgent 第一阶段上下文协议。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .planning import CurrentPlanRef

DynamicObject = dict[str, object]
ExecutionSource = Literal["react", "planning", "tool", "mcp", "llm", "guardrails"]


class ContextSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perception: DynamicObject = Field(default_factory=dict)
    stm: DynamicObject = Field(default_factory=dict)
    current_plan: CurrentPlanRef | None
    skill_context: DynamicObject = Field(default_factory=dict)
    last_observation: DynamicObject | None = None


class ExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    session_id: str
    plan_id: str | None
    trace_id: str
    source: ExecutionSource

