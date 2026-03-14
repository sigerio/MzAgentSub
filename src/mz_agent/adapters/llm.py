"""MzAgent 第一阶段 LLM 适配层。"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..config import RuntimeSettings, load_runtime_settings
from ..contracts.context import ExecutionContext
from ..contracts.llm import (
    LLMContentBlock,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderTrace,
)


class LLMAdapter:
    def __init__(
        self,
        *,
        responder: Callable[[LLMRequest], object] | None = None,
        project_root: str | Path | None = None,
        settings: RuntimeSettings | None = None,
        client_factory: Callable[[RuntimeSettings], object] | None = None,
        live_mode: bool | None = None,
    ) -> None:
        self._responder = responder
        self._settings = settings or load_runtime_settings(project_root)
        self._client_factory = client_factory
        self._client: object | None = None
        self._live_mode = live_mode if live_mode is not None else client_factory is not None

    def respond(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
    ) -> LLMResponse:
        raw_result = self._responder(request) if self._responder is not None else None

        if isinstance(raw_result, LLMResponse):
            return raw_result

        if isinstance(raw_result, dict):
            return LLMResponse.model_validate(raw_result)

        if isinstance(raw_result, str):
            return self._build_stub_response(
                request=request,
                execution_context=execution_context,
                text=raw_result,
            )

        if self._live_mode and self._settings.llm.is_configured():
            try:
                return self._respond_via_provider(
                    request=request,
                    execution_context=execution_context,
                )
            except ModuleNotFoundError as exc:
                if exc.name != "openai":
                    raise

        return self._build_stub_response(
            request=request,
            execution_context=execution_context,
            text=self._default_text(request=request),
        )

    def _respond_via_provider(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
    ) -> LLMResponse:
        client = self._get_client()
        model_name = request.route_hint or self._settings.llm.model_id or "openai-default"
        start_time = time.perf_counter()
        response = client.responses.create(
            model=model_name,
            input=self._build_input_messages(request=request),
            instructions=self._build_instructions(request=request),
            tools=request.tool_schemas or None,
            timeout=request.timeout / 1000,
        )
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        return self._normalize_provider_response(
            request=request,
            execution_context=execution_context,
            model_name=model_name,
            response=response,
            latency_ms=latency_ms,
        )

    def _get_client(self) -> object:
        if self._client is not None:
            return self._client

        if self._client_factory is not None:
            self._client = self._client_factory(self._settings)
            return self._client

        from openai import OpenAI

        self._client = OpenAI(
            api_key=self._settings.llm.api_key,
            base_url=self._settings.llm.base_url,
            timeout=self._settings.llm.timeout,
        )
        return self._client

    def _normalize_provider_response(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
        model_name: str,
        response: object,
        latency_ms: int,
    ) -> LLMResponse:
        content_blocks = self._extract_content_blocks(response=response)
        if not content_blocks:
            content_blocks = [
                LLMContentBlock(
                    type="text",
                    content=self._extract_output_text(response=response),
                )
            ]

        tool_calls = self._extract_tool_calls(response=response)
        usage = self._extract_usage(response=response)
        provider_trace = ProviderTrace(
            provider="openai",
            model=model_name,
            api_mode="responses",
            stream=request.stream,
            attempt=1,
        )
        raw_response_meta: dict[str, object] = {"trace_id": execution_context.trace_id}

        response_id = getattr(response, "id", None)
        if response_id is not None:
            raw_response_meta["response_id"] = str(response_id)
        request_id = getattr(response, "_request_id", None)
        if request_id is not None:
            raw_response_meta["request_id"] = str(request_id)

        finish_reason = self._extract_finish_reason(response=response)
        return LLMResponse(
            content_blocks=content_blocks,
            tool_calls=tool_calls,
            usage=usage,
            provider_trace=provider_trace,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            raw_response_meta=raw_response_meta,
        )

    def _build_stub_response(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
        text: str,
    ) -> LLMResponse:
        completion_tokens = max(1, len(text) // 8) if text else 1
        return LLMResponse(
            content_blocks=[LLMContentBlock(type="text", content=text)],
            tool_calls=[],
            usage=LLMUsage(
                prompt_tokens=len(request.messages),
                completion_tokens=completion_tokens,
                total_tokens=len(request.messages) + completion_tokens,
            ),
            provider_trace=ProviderTrace(
                provider="openai",
                model=request.route_hint or "openai-default",
                api_mode="stub",
                stream=request.stream,
                attempt=1,
            ),
            finish_reason="stop",
            latency_ms=0,
            raw_response_meta={"trace_id": execution_context.trace_id},
        )

    @staticmethod
    def _default_text(*, request: LLMRequest) -> str:
        if request.messages:
            return request.messages[-1].content
        return ""

    @staticmethod
    def _build_instructions(*, request: LLMRequest) -> str | None:
        instructions = [message.content for message in request.messages if message.role == "system"]
        if not instructions:
            return None
        return "\n\n".join(instructions)

    @staticmethod
    def _build_input_messages(*, request: LLMRequest) -> list[dict[str, str]] | str:
        messages = [
            {"role": message.role, "content": message.content}
            for message in request.messages
            if message.role != "system"
        ]
        if not messages:
            return ""
        return messages

    @staticmethod
    def _extract_output_text(*, response: object) -> str:
        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text
        return ""

    @staticmethod
    def _extract_content_blocks(*, response: object) -> list[LLMContentBlock]:
        blocks: list[LLMContentBlock] = []
        output = getattr(response, "output", None)
        if not isinstance(output, list):
            return blocks

        for item in output:
            content = getattr(item, "content", None)
            if not isinstance(content, list):
                continue
            for part in content:
                part_type = getattr(part, "type", None)
                if part_type == "output_text":
                    text = getattr(part, "text", "")
                    if isinstance(text, str):
                        blocks.append(LLMContentBlock(type="text", content=text))
                    continue
                if part_type == "reasoning" or part_type == "summary_text":
                    text = getattr(part, "text", "")
                    if isinstance(text, str):
                        blocks.append(LLMContentBlock(type="thinking", content=text))
        return blocks

    @staticmethod
    def _extract_tool_calls(*, response: object) -> list[dict[str, object]]:
        calls: list[dict[str, object]] = []
        output = getattr(response, "output", None)
        if not isinstance(output, list):
            return calls

        for item in output:
            item_type = getattr(item, "type", None)
            if item_type != "function_call":
                continue
            calls.append(
                {
                    "id": getattr(item, "id", None),
                    "call_id": getattr(item, "call_id", None),
                    "name": getattr(item, "name", None),
                    "arguments": getattr(item, "arguments", None),
                }
            )
        return calls

    @staticmethod
    def _extract_usage(*, response: object) -> LLMUsage | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None

        prompt_tokens = _coerce_int(
            getattr(usage, "input_tokens", None),
            getattr(usage, "prompt_tokens", None),
            default=0,
        )
        completion_tokens = _coerce_int(
            getattr(usage, "output_tokens", None),
            getattr(usage, "completion_tokens", None),
            default=0,
        )
        total_tokens = _coerce_int(
            getattr(usage, "total_tokens", None),
            default=prompt_tokens + completion_tokens,
        )
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _extract_finish_reason(*, response: object) -> str:
        status = getattr(response, "status", None)
        if isinstance(status, str) and status:
            return status
        return "stop"


def _coerce_int(*values: object, default: int) -> int:
    for value in values:
        if isinstance(value, int):
            return value
    return default
