"""MzAgent 最小 Web API 与单页入口。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote

from ..app import ConversationService, RuntimeOptions
from ..app.conversation import ConnectionPayload, ProfilePayload, RoundSubmission
from ..capabilities import CapabilityItem, CapabilityType

STATIC_ROOT = Path(__file__).resolve().parent / "static"


class MzAgentWebApp:
    def __init__(self, *, service: ConversationService) -> None:
        self._service = service

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await _send_response(send, status=404, body=b"Not Found", content_type="text/plain; charset=utf-8")
            return

        method = scope["method"].upper()
        path = scope["path"]
        query = parse_qs(scope.get("query_string", b"").decode("utf-8"))

        try:
            if method == "GET" and path == "/":
                await self._serve_index(send=send)
                return
            if method == "GET" and path.startswith("/static/"):
                await self._serve_static(path=path, send=send)
                return
            if method == "POST" and path == "/api/round":
                payload = await _read_json_body(receive=receive)
                submission = RoundSubmission.model_validate(payload)
                response = self._service.submit_round(submission=submission)
                await _send_json(send, status=200, payload=response.model_dump(mode="json"))
                return
            if method == "GET" and path == "/api/agent/stream":
                await self._handle_agent_stream(query=query, send=send)
                return
            if path.startswith("/api/llm/"):
                await self._handle_profile_routes(
                    method=method,
                    path=path,
                    receive=receive,
                    send=send,
                )
                return
            if path.startswith("/api/capabilities/"):
                await self._handle_capability_routes(
                    method=method,
                    path=path,
                    receive=receive,
                    send=send,
                )
                return
            if path.startswith("/api/session/"):
                await self._handle_session_routes(
                    method=method,
                    path=path,
                    send=send,
                )
                return
        except ValueError as exc:
            await _send_json(
                send,
                status=400,
                payload={"error_code": "invalid_request", "message": str(exc)},
            )
            return
        except json.JSONDecodeError:
            await _send_json(
                send,
                status=400,
                payload={"error_code": "invalid_json", "message": "请求体不是合法 JSON。"},
            )
            return
        except Exception as exc:
            await _send_json(
                send,
                status=500,
                payload={"error_code": "internal_error", "message": f"服务内部错误：{exc}"},
            )
            return

        await _send_json(
            send,
            status=404,
            payload={"error_code": "not_found", "message": f"未找到路径：{path}"},
        )

    async def _handle_session_routes(self, *, method: str, path: str, send: Any) -> None:
        parts = path.strip("/").split("/")
        if len(parts) < 4:
            raise ValueError("会话路径不完整。")
        session_id = parts[2]
        self._service.ensure_session(session_id=session_id)

        if (
            len(parts) == 6
            and parts[3] == "rounds"
            and parts[5] == "retry"
            and method == "POST"
        ):
            response = self._service.retry_round(round_id=unquote(parts[4]))
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return

        action = parts[3]

        if method == "GET" and action == "history":
            response = self._service.get_history()
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if method == "GET" and action == "status":
            response = self._service.get_status()
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if method == "POST" and action == "reset":
            response = self._service.reset_session()
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        raise ValueError(f"不支持的会话操作：{method} {action}")

    async def _handle_profile_routes(
        self,
        *,
        method: str,
        path: str,
        receive: Any,
        send: Any,
    ) -> None:
        parts = path.strip("/").split("/")
        if parts == ["api", "llm", "profiles"] and method == "GET":
            response = self._service.list_profiles()
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if parts == ["api", "llm", "connection"] and method == "POST":
            payload = ConnectionPayload.model_validate(await _read_json_body(receive=receive))
            response = self._service.save_connection(payload=payload)
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if parts == ["api", "llm", "connection", "models"] and method in {"GET", "POST"}:
            response = self._service.discover_connection_models()
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if parts == ["api", "llm", "profiles"] and method == "POST":
            payload = ProfilePayload.model_validate(await _read_json_body(receive=receive))
            response = self._service.save_profile(payload=payload)
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if (
            len(parts) == 5
            and parts[:3] == ["api", "llm", "profiles"]
            and parts[4] == "test"
            and method == "POST"
        ):
            response = self._service.test_profile_connection(profile_name=unquote(parts[3]))
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if len(parts) == 4 and parts[:3] == ["api", "llm", "profiles"] and method == "DELETE":
            response = self._service.delete_profile(profile_name=parts[3])
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if (
            len(parts) == 5
            and parts[:3] == ["api", "llm", "profiles"]
            and parts[4] == "activate"
            and method == "POST"
        ):
            response = self._service.activate_profile(profile_name=parts[3])
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        raise ValueError(f"不支持的配置方案操作：{method} {path}")

    async def _handle_capability_routes(
        self,
        *,
        method: str,
        path: str,
        receive: Any,
        send: Any,
    ) -> None:
        parts = path.strip("/").split("/")
        if len(parts) < 3 or parts[:2] != ["api", "capabilities"]:
            raise ValueError(f"不支持的能力操作：{method} {path}")

        capability_type = _parse_capability_type(parts[2])
        if len(parts) == 3 and method == "GET":
            response = self._service.list_capabilities(capability_type=capability_type)
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if len(parts) == 3 and method == "POST":
            payload = CapabilityItem.model_validate(await _read_json_body(receive=receive))
            response = self._service.save_capability(
                capability_type=capability_type,
                item=payload,
            )
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if len(parts) == 4 and method == "DELETE":
            response = self._service.delete_capability(
                capability_type=capability_type,
                name=unquote(parts[3]),
            )
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        if len(parts) == 5 and parts[4] == "toggle" and method == "POST":
            response = self._service.toggle_capability(
                capability_type=capability_type,
                name=unquote(parts[3]),
            )
            await _send_json(send, status=200, payload=response.model_dump(mode="json"))
            return
        raise ValueError(f"不支持的能力操作：{method} {path}")

    async def _handle_agent_stream(
        self,
        *,
        query: dict[str, list[str]],
        send: Any,
    ) -> None:
        session_id = query.get("session_id", [self._service.session_id])[0]
        self._service.ensure_session(session_id=session_id)
        status = self._service.get_status().model_dump(mode="json")
        history = self._service.get_history().model_dump(mode="json")
        body = b"".join(
            [
                _encode_sse_event(event="session_ready", payload={"session_id": session_id}),
                _encode_sse_event(event="session_status", payload=status),
                _encode_sse_event(event="session_history", payload=history),
                _encode_sse_event(event="stream_end", payload={"done": True}),
            ]
        )
        await _send_response(
            send,
            status=200,
            body=body,
            content_type="text/event-stream; charset=utf-8",
            extra_headers=[
                (b"cache-control", b"no-cache"),
                (b"x-accel-buffering", b"no"),
            ],
        )

    async def _serve_index(self, *, send: Any) -> None:
        template = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        html = template.replace("__SESSION_ID__", self._service.session_id)
        await _send_response(
            send,
            status=200,
            body=html.encode("utf-8"),
            content_type="text/html; charset=utf-8",
        )

    async def _serve_static(self, *, path: str, send: Any) -> None:
        relative_path = path.removeprefix("/static/")
        file_path = (STATIC_ROOT / relative_path).resolve()
        if not file_path.is_file() or STATIC_ROOT not in file_path.parents:
            raise ValueError("静态资源不存在。")

        content_type = "text/plain; charset=utf-8"
        if file_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif file_path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"

        await _send_response(
            send,
            status=200,
            body=file_path.read_bytes(),
            content_type=content_type,
        )


def create_app(
    *,
    project_root: Path | None = None,
    options: RuntimeOptions | None = None,
    service: ConversationService | None = None,
) -> MzAgentWebApp:
    if service is None:
        resolved_root = project_root or Path(__file__).resolve().parents[3]
        service = ConversationService(project_root=resolved_root, options=options)
    return MzAgentWebApp(service=service)


async def _read_json_body(*, receive: Any) -> dict[str, Any]:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    payload = b"".join(chunks)
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


async def _send_json(send: Any, *, status: int, payload: dict[str, Any]) -> None:
    await _send_response(
        send,
        status=status,
        body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        content_type="application/json; charset=utf-8",
    )


async def _send_response(
    send: Any,
    *,
    status: int,
    body: bytes,
    content_type: str,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    headers = [
        (b"content-type", content_type.encode("utf-8")),
        (b"content-length", str(len(body)).encode("utf-8")),
    ]
    headers.extend(extra_headers or [])
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        }
    )


def _parse_capability_type(value: str) -> CapabilityType:
    normalized = value.strip().lower()
    if normalized not in {"tool", "mcp", "skill"}:
        raise ValueError(f"不支持的能力类型：{value}")
    return normalized  # type: ignore[return-value]


def _encode_sse_event(*, event: str, payload: dict[str, object]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
