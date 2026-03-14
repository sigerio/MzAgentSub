"""MzAgent 第一阶段回写门禁。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..contracts.context import ExecutionContext
from ..contracts.planning import CurrentStep
from ..contracts.state import ReactStatus
from .errors import DomainValidationError

WritebackStage = Literal["pre_action", "post_action", "pre_answer", "post_answer"]
DynamicObject = dict[str, object]


class WritebackRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: WritebackStage
    execution_context: ExecutionContext
    react_status: ReactStatus
    current_step: CurrentStep | None
    observation: DynamicObject | None = None
    final_answer: str | None = None
    metadata: DynamicObject = Field(default_factory=dict)


def ensure_writeback_stage(*, stage: WritebackStage) -> None:
    if stage not in {"post_action", "post_answer"}:
        raise DomainValidationError("STM 回写只能发生在 post_action 或 post_answer 之后。")


def prepare_writeback_record(
    *,
    stage: WritebackStage,
    execution_context: ExecutionContext,
    react_status: ReactStatus,
    current_step: CurrentStep | None,
    observation: DynamicObject | None = None,
    final_answer: str | None = None,
    metadata: DynamicObject | None = None,
) -> WritebackRecord:
    ensure_writeback_stage(stage=stage)
    if react_status is ReactStatus.FINISHED and current_step is not None:
        raise DomainValidationError("完成态回写前必须先清空 current_step。")
    if react_status in {ReactStatus.BLOCKED, ReactStatus.DEGRADED} and final_answer is not None:
        raise DomainValidationError("阻断态或降级态回写不得携带最终答复。")
    return WritebackRecord(
        stage=stage,
        execution_context=execution_context,
        react_status=react_status,
        current_step=current_step,
        observation=observation,
        final_answer=final_answer,
        metadata=metadata or {},
    )

