from __future__ import annotations

import io
import json
from pathlib import Path
from urllib.error import HTTPError

from mz_agent.app.conversation import ConversationService
from mz_agent.http_headers import DEFAULT_USER_AGENT
from mz_agent.llm_profiles import LLMConnection


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_model_discovery_uses_tokenauth_headers_then_falls_back(monkeypatch, tmp_path: Path) -> None:
    request_headers: list[dict[str, str]] = []

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 20
        request_headers.append(dict(request.header_items()))
        if len(request_headers) == 1:
            raise HTTPError(
                request.full_url,
                403,
                "Forbidden",
                hdrs=None,
                fp=io.BytesIO('{"message":"接口返回异常状态：403"}'.encode("utf-8")),
            )
        return _FakeHTTPResponse(
            {
                "data": [
                    {"id": "gpt-4.1"},
                    {"id": "models/claude-3-7-sonnet"},
                ]
            }
        )

    monkeypatch.setattr("mz_agent.app.conversation.urllib_request.urlopen", fake_urlopen)

    models = ConversationService._fetch_connection_model_names(
        connection=LLMConnection(
            base_url="https://example.com/v1",
            api_key="sk-demo",
            timeout=60,
        )
    )

    assert len(request_headers) == 2
    assert request_headers[0]["Authorization"] == "Bearer sk-demo"
    assert request_headers[0]["X-api-key"] == "sk-demo"
    assert request_headers[0]["User-agent"] == DEFAULT_USER_AGENT
    assert request_headers[1]["Authorization"] == "Bearer sk-demo"
    assert "X-api-key" not in request_headers[1]
    assert request_headers[1]["User-agent"] == DEFAULT_USER_AGENT
    assert models == ["claude-3-7-sonnet", "gpt-4.1"]
