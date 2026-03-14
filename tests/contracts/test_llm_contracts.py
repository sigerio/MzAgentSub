from mz_agent.contracts.llm import (
    LLMContentBlock,
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    ProviderTrace,
)


def test_llm_request_accepts_minimal_valid_payload() -> None:
    request = LLMRequest(
        messages=[LLMMessage(role="user", content="你好")],
        model_policy="quality",
        tool_schemas=[{"name": "echo"}],
        response_schema={"type": "object"},
    )

    assert request.model_dump(mode="json") == {
        "messages": [{"role": "user", "content": "你好"}],
        "model_policy": "quality",
        "route_hint": None,
        "tool_schemas": [{"name": "echo"}],
        "response_schema": {"type": "object"},
        "stream": False,
        "timeout": 30000,
    }


def test_llm_response_dump_is_stable() -> None:
    response = LLMResponse(
        content_blocks=[LLMContentBlock(type="text", content="ok")],
        tool_calls=[{"name": "echo"}],
        usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        provider_trace=ProviderTrace(
            provider="openai",
            model="gpt-test",
            api_mode="chat",
            stream=False,
            attempt=1,
        ),
        finish_reason="stop",
        latency_ms=12,
        raw_response_meta={"trace_id": "trace_001"},
    )

    assert response.model_dump(mode="json") == {
        "content_blocks": [{"type": "text", "content": "ok"}],
        "tool_calls": [{"name": "echo"}],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
        },
        "provider_trace": {
            "provider": "openai",
            "model": "gpt-test",
            "api_mode": "chat",
            "stream": False,
            "attempt": 1,
        },
        "finish_reason": "stop",
        "latency_ms": 12,
        "raw_response_meta": {"trace_id": "trace_001"},
    }

