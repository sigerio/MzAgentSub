"""MzAgent 第一阶段动作协议。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .state import ReactStatus
from ..runtime.errors import DomainValidationError

ActionType = Literal["skill", "tool", "mcp", "rag", "llm", "clarify", "finish"]
ActionAvailability = Literal["available", "unavailable", "constrained"]
DynamicObject = dict[str, object]


class AvailableAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    targets: list[str] = Field(default_factory=list)
    availability: ActionAvailability


class NextAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    action_target: str | None
    action_input: DynamicObject = Field(default_factory=dict)


class ReActResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_action: NextAction | None
    final_answer: str | None
    react_status: ReactStatus


def build_react_result(
    *,
    react_status: ReactStatus,
    next_action: NextAction | None = None,
    final_answer: str | None = None,
) -> ReActResult:
    if react_status is ReactStatus.RUNNING:
        if next_action is None:
            raise DomainValidationError("运行态结果必须保留下一步动作。")
        if final_answer is not None:
            raise DomainValidationError("运行态结果不得携带最终答复。")
    elif react_status is ReactStatus.FINISHED:
        if next_action is not None:
            raise DomainValidationError("完成态结果不得继续保留动作。")
        if final_answer is None:
            raise DomainValidationError("完成态结果必须携带最终答复。")
    else:
        if next_action is not None:
            raise DomainValidationError("阻断态或降级态结果不得继续保留动作。")
        if final_answer is not None:
            raise DomainValidationError("阻断态或降级态结果不得携带最终答复。")

    return ReActResult(
        next_action=next_action,
        final_answer=final_answer,
        react_status=react_status,
    )

