"""MzAgent 第一阶段状态枚举。"""

from enum import Enum


class StepState(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ABANDONED = "abandoned"


class CursorState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class ReactStatus(str, Enum):
    RUNNING = "running"
    FINISHED = "finished"
    BLOCKED = "blocked"
    DEGRADED = "degraded"


class GuardrailsDecisionKind(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    DEGRADE = "degrade"
    CLARIFY = "clarify"

