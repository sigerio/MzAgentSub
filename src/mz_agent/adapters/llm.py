"""MzAgent 第一阶段 LLM 适配层。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from ..config import LLMSettings, RuntimeSettings, load_runtime_settings
from ..contracts.context import ExecutionContext
from ..http_headers import build_default_http_headers
from ..contracts.llm import (
    LLMContentBlock,
    LLMMessage,
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
        self._project_root = project_root
        self._settings = settings or (self._build_stub_settings() if project_root is None else None)
        self._client_factory = client_factory
        self._live_mode = live_mode if live_mode is not None else client_factory is not None

    def respond(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
    ) -> LLMResponse:
        settings = self._resolve_settings(request=request)
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
                settings=settings,
            )

        if self._live_mode and settings.llm.is_configured():
            try:
                return self._respond_via_provider(
                    request=request,
                    execution_context=execution_context,
                    settings=settings,
                )
            except ModuleNotFoundError as exc:
                if exc.name != "openai":
                    raise

        return self._build_stub_response(
            request=request,
            execution_context=execution_context,
            text=self._default_text(request=request),
            settings=settings,
        )

    def test_connection(
        self,
        *,
        profile_name: str,
        timeout_ms: int = 10_000,
    ) -> LLMResponse:
        request = LLMRequest(
            messages=[LLMMessage(role="user", content="请只回复：PING_OK")],
            model_policy="connection_test",
            profile_name=profile_name,
            stream=False,
            timeout=timeout_ms,
        )
        settings = self._resolve_settings(request=request)
        if not settings.llm.is_configured():
            raise ValueError("当前配置方案不完整，请先补齐模型与密钥配置。")
        if not self._live_mode:
            raise RuntimeError("当前 LLM 适配器未启用真实连接测试模式。")

        return self._respond_via_provider(
            request=request,
            execution_context=ExecutionContext(
                request_id="req_profile_test",
                session_id="sess_profile_test",
                plan_id=None,
                trace_id="trace_profile_test",
                source="llm",
            ),
            settings=settings,
        )

    def _respond_via_provider(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
        settings: RuntimeSettings,
    ) -> LLMResponse:
        model_name = request.route_hint or settings.llm.model_id or "openai-default"
        api_mode = settings.llm.api_mode

        if api_mode == "openai-responses":
            client = self._get_client(settings=settings)
            start_time = time.perf_counter()
            request_payload: dict[str, object] = {
                "model": model_name,
                "input": self._build_input_messages(request=request),
                "timeout": request.timeout / 1000,
            }
            instructions = self._build_instructions(request=request)
            if instructions is not None:
                request_payload["instructions"] = instructions
            if request.tool_schemas:
                request_payload["tools"] = request.tool_schemas
            response = client.responses.create(**request_payload)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return self._normalize_responses_api_response(
                request=request,
                execution_context=execution_context,
                settings=settings,
                model_name=model_name,
                response=response,
                latency_ms=latency_ms,
            )

        if api_mode == "openai-completions":
            client = self._get_client(settings=settings)
            start_time = time.perf_counter()
            response = client.chat.completions.create(
                model=model_name,
                messages=self._build_chat_completion_messages(request=request),
                tools=request.tool_schemas or None,
                timeout=request.timeout / 1000,
            )
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return self._normalize_chat_completion_response(
                request=request,
                execution_context=execution_context,
                settings=settings,
                model_name=model_name,
                response=response,
                latency_ms=latency_ms,
            )

        if api_mode == "anthropic-messages":
            start_time = time.perf_counter()
            response = self._post_anthropic_messages(
                request=request,
                settings=settings,
                model_name=model_name,
            )
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            return self._normalize_anthropic_messages_response(
                request=request,
                execution_context=execution_context,
                settings=settings,
                model_name=model_name,
                response=response,
                latency_ms=latency_ms,
            )

        raise ValueError(f"不支持的模型协议：{api_mode}")

    def _get_client(self, *, settings: RuntimeSettings) -> object:
        if self._client_factory is not None:
            return self._client_factory(settings)

        from openai import OpenAI

        return OpenAI(
            api_key=settings.llm.api_key,
            base_url=settings.llm.base_url,
            timeout=settings.llm.timeout,
            default_headers=build_default_http_headers(settings.llm.extra_headers),
        )

    def _normalize_responses_api_response(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
        settings: RuntimeSettings,
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
            provider="newapi",
            model=model_name,
            api_mode=settings.llm.api_mode,
            profile_name=settings.llm.profile_name,
            stream=request.stream,
            attempt=1,
        )
        raw_response_meta: dict[str, object] = {
            "trace_id": execution_context.trace_id,
            "profile_name": settings.llm.profile_name,
        }

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

    def _normalize_chat_completion_response(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
        settings: RuntimeSettings,
        model_name: str,
        response: object,
        latency_ms: int,
    ) -> LLMResponse:
        choice = _first_item(_read_value(response, "choices"), default=None)
        message = _read_value(choice, "message", default=None)
        message_content = _read_value(message, "content", default="")
        text_content = message_content if isinstance(message_content, str) else ""

        content_blocks = []
        if text_content:
            content_blocks.append(LLMContentBlock(type="text", content=text_content))

        tool_calls: list[dict[str, object]] = []
        raw_tool_calls = _read_value(message, "tool_calls", default=[])
        if isinstance(raw_tool_calls, list):
            for item in raw_tool_calls:
                function = _read_value(item, "function", default=None)
                tool_calls.append(
                    {
                        "id": _read_value(item, "id", default=None),
                        "call_id": _read_value(item, "id", default=None),
                        "name": _read_value(function, "name", default=None),
                        "arguments": _read_value(function, "arguments", default=None),
                    }
                )

        provider_trace = ProviderTrace(
            provider="newapi",
            model=model_name,
            api_mode=settings.llm.api_mode,
            profile_name=settings.llm.profile_name,
            stream=request.stream,
            attempt=1,
        )
        raw_response_meta: dict[str, object] = {
            "trace_id": execution_context.trace_id,
            "profile_name": settings.llm.profile_name,
        }

        response_id = _read_value(response, "id", default=None)
        if response_id is not None:
            raw_response_meta["response_id"] = str(response_id)
        request_id = _read_value(response, "_request_id", default=None)
        if request_id is not None:
            raw_response_meta["request_id"] = str(request_id)

        finish_reason = _read_value(choice, "finish_reason", default="stop")
        if not isinstance(finish_reason, str) or not finish_reason:
            finish_reason = "stop"

        return LLMResponse(
            content_blocks=content_blocks,
            tool_calls=tool_calls,
            usage=self._extract_usage(response=response),
            provider_trace=provider_trace,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            raw_response_meta=raw_response_meta,
        )

    def _normalize_anthropic_messages_response(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
        settings: RuntimeSettings,
        model_name: str,
        response: dict[str, object],
        latency_ms: int,
    ) -> LLMResponse:
        content_blocks: list[LLMContentBlock] = []
        tool_calls: list[dict[str, object]] = []

        raw_content = response.get("content")
        if isinstance(raw_content, list):
            for item in raw_content:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").strip()
                if item_type == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        content_blocks.append(LLMContentBlock(type="text", content=text))
                    continue
                if item_type in {"thinking", "redacted_thinking"}:
                    thinking = item.get("thinking")
                    if isinstance(thinking, str) and thinking:
                        content_blocks.append(LLMContentBlock(type="thinking", content=thinking))
                    continue
                if item_type == "tool_use":
                    tool_input = item.get("input")
                    tool_calls.append(
                        {
                            "id": item.get("id"),
                            "call_id": item.get("id"),
                            "name": item.get("name"),
                            "arguments": json.dumps(tool_input, ensure_ascii=False)
                            if tool_input is not None
                            else "{}",
                        }
                    )

        provider_trace = ProviderTrace(
            provider="newapi",
            model=model_name,
            api_mode=settings.llm.api_mode,
            profile_name=settings.llm.profile_name,
            stream=request.stream,
            attempt=1,
        )
        raw_response_meta: dict[str, object] = {
            "trace_id": execution_context.trace_id,
            "profile_name": settings.llm.profile_name,
        }
        response_id = response.get("id")
        if response_id is not None:
            raw_response_meta["response_id"] = str(response_id)

        finish_reason = response.get("stop_reason")
        if not isinstance(finish_reason, str) or not finish_reason:
            finish_reason = "stop"

        return LLMResponse(
            content_blocks=content_blocks,
            tool_calls=tool_calls,
            usage=self._extract_usage(response=response),
            provider_trace=provider_trace,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            raw_response_meta=raw_response_meta,
        )

    def _post_anthropic_messages(
        self,
        *,
        request: LLMRequest,
        settings: RuntimeSettings,
        model_name: str,
    ) -> dict[str, object]:
        endpoint = f"{(settings.llm.base_url or '').rstrip('/')}/messages"
        payload: dict[str, object] = {
            "model": model_name,
            "messages": self._build_anthropic_messages(request=request),
            "max_tokens": 4096,
            "stream": False,
        }
        instructions = self._build_instructions(request=request)
        if instructions:
            payload["system"] = instructions
        tools = self._build_anthropic_tools(request=request)
        if tools:
            payload["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-api-key": settings.llm.api_key or "",
            "anthropic-version": "2023-06-01",
            **build_default_http_headers(settings.llm.extra_headers),
        }
        request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = urllib_request.Request(
            endpoint,
            data=request_body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(http_request, timeout=request.timeout / 1000) as response:
                body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise ProviderRequestError(
                message=_extract_provider_error_message(body) or f"接口返回异常状态：{exc.code}",
                status_code=exc.code,
                response_body=body,
            ) from exc
        except urllib_error.URLError as exc:
            raise ProviderRequestError(
                message=f"连接失败：{exc.reason}",
                status_code=None,
                response_body=None,
            ) from exc

        payload_data = json.loads(body)
        if not isinstance(payload_data, dict):
            raise ValueError("Claude Messages 返回格式不正确。")
        return payload_data

    def _build_stub_response(
        self,
        *,
        request: LLMRequest,
        execution_context: ExecutionContext,
        text: str,
        settings: RuntimeSettings,
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
                provider="newapi",
                model=request.route_hint or settings.llm.model_id or "openai-default",
                api_mode="stub",
                profile_name=settings.llm.profile_name,
                stream=request.stream,
                attempt=1,
            ),
            finish_reason="stop",
            latency_ms=0,
            raw_response_meta={
                "trace_id": execution_context.trace_id,
                "profile_name": settings.llm.profile_name,
            },
        )

    def _resolve_settings(self, *, request: LLMRequest) -> RuntimeSettings:
        if self._project_root is not None:
            return load_runtime_settings(self._project_root, profile_name=request.profile_name)
        if self._settings is None:
            raise ValueError("当前未加载 LLM 运行配置。")
        if request.profile_name and not self._settings.llm.profile_name and not self._settings.llm.is_configured():
            return self._settings.model_copy(
                update={
                    "active_profile_name": request.profile_name,
                    "llm": self._settings.llm.model_copy(
                        update={"profile_name": request.profile_name}
                    ),
                }
            )
        if request.profile_name and request.profile_name != self._settings.llm.profile_name:
            raise ValueError(f"当前运行时未加载配置方案：{request.profile_name}")
        return self._settings

    @staticmethod
    def _build_stub_settings() -> RuntimeSettings:
        return RuntimeSettings(
            project_root=Path.cwd(),
            llm=LLMSettings(),
            active_profile_name=None,
            llm_profiles={},
            mcp_servers={},
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
    def _build_chat_completion_messages(*, request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        instructions = LLMAdapter._build_instructions(request=request)
        if instructions:
            messages.append({"role": "system", "content": instructions})
        for message in request.messages:
            if message.role == "system":
                continue
            role = message.role if message.role in {"user", "assistant"} else "user"
            messages.append({"role": role, "content": message.content})
        return messages or [{"role": "user", "content": ""}]

    @staticmethod
    def _build_anthropic_messages(*, request: LLMRequest) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for message in request.messages:
            if message.role == "system":
                continue
            role = "assistant" if message.role == "assistant" else "user"
            messages.append(
                {
                    "role": role,
                    "content": [
                        {
                            "type": "text",
                            "text": message.content,
                        }
                    ],
                }
            )
        return messages or [{"role": "user", "content": [{"type": "text", "text": ""}]}]

    @staticmethod
    def _build_anthropic_tools(*, request: LLMRequest) -> list[dict[str, object]]:
        tools: list[dict[str, object]] = []
        for schema in request.tool_schemas:
            if not isinstance(schema, dict):
                continue
            function = schema.get("function")
            if isinstance(function, dict):
                name = function.get("name")
                description = function.get("description")
                input_schema = function.get("parameters")
            else:
                name = schema.get("name")
                description = schema.get("description")
                input_schema = schema.get("input_schema")
            if not isinstance(name, str) or not name.strip():
                continue
            tools.append(
                {
                    "name": name.strip(),
                    "description": str(description or "").strip(),
                    "input_schema": input_schema if isinstance(input_schema, dict) else {"type": "object"},
                }
            )
        return tools

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
        usage = _read_value(response, "usage", default=None)
        if usage is None:
            return None

        prompt_tokens = _coerce_int(
            _read_value(usage, "input_tokens", default=None),
            _read_value(usage, "prompt_tokens", default=None),
            default=0,
        )
        completion_tokens = _coerce_int(
            _read_value(usage, "output_tokens", default=None),
            _read_value(usage, "completion_tokens", default=None),
            default=0,
        )
        total_tokens = _coerce_int(
            _read_value(usage, "total_tokens", default=None),
            default=prompt_tokens + completion_tokens,
        )
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _extract_finish_reason(*, response: object) -> str:
        status = _read_value(response, "status", default=None)
        if isinstance(status, str) and status:
            return status
        return "stop"


class ProviderRequestError(RuntimeError):
    def __init__(
        self,
        *,
        message: str,
        status_code: int | None,
        response_body: str | None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def _coerce_int(*values: object, default: int) -> int:
    for value in values:
        if isinstance(value, int):
            return value
    return default


def _read_value(source: object, key: str, *, default: object = None) -> object:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _first_item(items: object, *, default: object) -> object:
    if isinstance(items, list) and items:
        return items[0]
    return default


def _extract_provider_error_message(body: str) -> str | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    raw_error = payload.get("error")
    if isinstance(raw_error, dict):
        message = raw_error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return None
