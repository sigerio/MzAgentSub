"""MzAgent 第一阶段 Tool 与 MCP 协议。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ToolRiskLevel = Literal["low", "medium", "high"]
ToolExecutionStatus = Literal["success", "partial", "error"]
ToolCallerSource = Literal["llm", "system", "manual", "react"]
DynamicObject = dict[str, object]


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    name: str
    description: str
    input_schema: DynamicObject
    permission_domain: str
    risk_level: ToolRiskLevel
    idempotent: bool
    requires_confirmation: bool
    handler: Callable[..., object]
    result_schema_version: str = "v1"


class ToolExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeout_ms: int = Field(default=30_000, ge=1)
    retry_limit: int = Field(default=0, ge=0)
    idempotent: bool = False
    dry_run: bool = False


class ToolCallerContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: ToolCallerSource
    user_id: str | None = None
    trace_id: str
    plan_step_id: str | None = None


class ToolExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    session_id: str
    tool_name: str
    arguments: DynamicObject = Field(default_factory=dict)
    execution_policy: ToolExecutionPolicy
    caller_context: ToolCallerContext


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ToolExecutionStatus
    text: str
    data: DynamicObject | None = None
    error_code: str | None = None
    message: str | None = None
    result_schema_version: str = "v1"
    execution_meta: DynamicObject = Field(default_factory=dict)


class MCPBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    server_name: str
    transport: str
    tool_name: str
    enabled: bool = True
    timeout: int = Field(default=30_000, ge=1)
    namespace: str

