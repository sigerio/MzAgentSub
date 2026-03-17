"""MzAgent 第一阶段 LLM 协议。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DynamicObject = dict[str, object]
MessageRole = Literal["system", "user", "assistant", "tool"]
ContentBlockType = Literal["text", "tool_call", "thinking"]


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str


class LLMContentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ContentBlockType
    content: str


class LLMUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ProviderTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    api_mode: str
    profile_name: str | None = None
    stream: bool
    attempt: int = Field(default=1, ge=1)


class LLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[LLMMessage]
    model_policy: str
    profile_name: str | None = None
    route_hint: str | None = None
    tool_schemas: list[DynamicObject] = Field(default_factory=list)
    response_schema: DynamicObject | None = None
    stream: bool = False
    timeout: int = Field(default=30_000, ge=1)


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_blocks: list[LLMContentBlock] = Field(default_factory=list)
    tool_calls: list[DynamicObject] = Field(default_factory=list)
    usage: LLMUsage | None = None
    provider_trace: ProviderTrace | None = None
    finish_reason: str
    latency_ms: int = Field(default=0, ge=0)
    raw_response_meta: DynamicObject = Field(default_factory=dict)
