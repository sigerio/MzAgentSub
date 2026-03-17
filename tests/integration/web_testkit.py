from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from mz_agent.app import ConversationService, RuntimeOptions
from mz_agent.web import create_app


def build_test_app(tmp_path: Path, *, session_id: str = "sess_web_test"):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )
    options = RuntimeOptions(
        stm_path=".mz_agent/test_web_stm.json",
        session_id=session_id,
        request_prefix="req_web",
        trace_prefix="trace_web",
    )
    service = ConversationService(project_root=tmp_path, options=options)
    return create_app(service=service)


def call_app(app, *, method: str, path: str, payload: dict[str, object] | None = None):
    return asyncio.run(_call_app(app, method=method, path=path, payload=payload))


async def _call_app(app, *, method: str, path: str, payload: dict[str, object] | None = None):
    parsed = urlsplit(path)
    request_body = b""
    headers: list[tuple[bytes, bytes]] = []
    if payload is not None:
        request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers.append((b"content-type", b"application/json"))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": parsed.path,
        "raw_path": parsed.path.encode("utf-8"),
        "query_string": parsed.query.encode("utf-8"),
        "headers": headers,
    }

    sent = False
    messages: list[dict[str, object]] = []

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": request_body, "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)

    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    headers = dict(start["headers"])
    content_type = headers.get(b"content-type", b"").decode("utf-8")
    return {
        "status": start["status"],
        "headers": headers,
        "body": body,
        "json": json.loads(body.decode("utf-8")) if body and "application/json" in content_type else None,
        "text": body.decode("utf-8"),
    }
