"""MzAgent 第一阶段 MCP 适配层。"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from collections.abc import Awaitable, Callable
from pathlib import Path
import threading
from typing import Any, Protocol, TypeVar

from ..config import (
    LLMSettings,
    MCPServerSettings,
    RuntimeSettings,
    discover_project_root,
    load_pyproject,
    load_runtime_settings,
    parse_mcp_servers,
)
from ..contracts.context import ExecutionContext
from ..contracts.tooling import MCPBinding, ToolExecutionResult


class MCPClientProtocol(Protocol):
    def list_tools(self) -> list[dict[str, object]]:
        ...

    def call_tool(self, *, tool_name: str, arguments: dict[str, object]) -> ToolExecutionResult:
        ...


class MCPAdapter:
    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        settings: RuntimeSettings | None = None,
        client_factory: Callable[[MCPServerSettings], MCPClientProtocol] | None = None,
    ) -> None:
        self._bindings: dict[tuple[str, str], MCPBinding] = {}
        self._handlers: dict[tuple[str, str], Callable[..., object]] = {}
        self._settings = settings or self._load_settings(project_root=project_root)
        self._client_factory = client_factory

    def list_servers(self) -> list[MCPServerSettings]:
        return sorted(self._settings.mcp_servers.values(), key=lambda server: server.name)

    def register(
        self,
        *,
        binding: MCPBinding,
        handler: Callable[..., object],
    ) -> None:
        key = (binding.server_name, binding.tool_name)
        self._bindings[key] = binding
        self._handlers[key] = handler

    def list_capabilities(self, *, server_name: str) -> list[dict[str, object]]:
        capabilities: list[dict[str, object]] = []
        for (binding_server, tool_name), binding in self._bindings.items():
            if binding_server != server_name or not binding.enabled:
                continue
            capabilities.append(
                {
                    "server_name": binding.server_name,
                    "tool_name": tool_name,
                    "namespace": binding.namespace,
                    "transport": binding.transport,
                }
            )

        if capabilities:
            return capabilities

        server = self._settings.mcp_servers.get(server_name)
        if server is None or server.transport_type != "stdio":
            return []

        try:
            client = self._get_client(server=server)
            return client.list_tools()
        except Exception:
            return []

    def invoke(
        self,
        *,
        server_name: str,
        tool_name: str,
        arguments: dict[str, object],
        execution_context: ExecutionContext,
    ) -> ToolExecutionResult:
        key = (server_name, tool_name)
        binding = self._bindings.get(key)
        handler = self._handlers.get(key)
        if binding is not None and handler is not None and binding.enabled:
            return self._invoke_registered_handler(
                binding=binding,
                handler=handler,
                tool_name=tool_name,
                arguments=arguments,
                execution_context=execution_context,
            )

        server = self._settings.mcp_servers.get(server_name)
        if server is None:
            return ToolExecutionResult(
                status="error",
                text="",
                error_code="MCP_001",
                message="MCP 服务不可用或能力不存在。",
                execution_meta={"server_name": server_name, "tool_name": tool_name},
            )

        try:
            client = self._get_client(server=server)
            result = client.call_tool(tool_name=tool_name, arguments=arguments)
        except FileNotFoundError:
            return ToolExecutionResult(
                status="error",
                text="",
                error_code="MCP_001",
                message="MCP 可执行文件不存在。",
                execution_meta={"server_name": server_name, "tool_name": tool_name},
            )
        except Exception as exc:
            return ToolExecutionResult(
                status="error",
                text="",
                error_code="MCP_003",
                message=f"MCP 调用失败：{exc}",
                execution_meta={
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "trace_id": execution_context.trace_id,
                },
            )

        result.execution_meta = {
            **result.execution_meta,
            "server_name": server_name,
            "tool_name": tool_name,
            "trace_id": execution_context.trace_id,
        }
        return result

    def _invoke_registered_handler(
        self,
        *,
        binding: MCPBinding,
        handler: Callable[..., object],
        tool_name: str,
        arguments: dict[str, object],
        execution_context: ExecutionContext,
    ) -> ToolExecutionResult:
        try:
            raw_result = handler(**arguments)
        except Exception as exc:
            return ToolExecutionResult(
                status="error",
                text="",
                error_code="MCP_003",
                message=f"MCP 调用失败：{exc}",
                execution_meta={
                    "server_name": binding.server_name,
                    "tool_name": tool_name,
                    "trace_id": execution_context.trace_id,
                },
            )

        if isinstance(raw_result, ToolExecutionResult):
            return raw_result
        if isinstance(raw_result, dict):
            text = raw_result.get("text")
            data = raw_result.get("data")
            return ToolExecutionResult(
                status="success",
                text=text if isinstance(text, str) else "",
                data=data if isinstance(data, dict) else None,
                execution_meta={"server_name": binding.server_name, "tool_name": tool_name},
            )
        return ToolExecutionResult(
            status="success",
            text=str(raw_result),
            execution_meta={"server_name": binding.server_name, "tool_name": tool_name},
        )

    def _get_client(self, *, server: MCPServerSettings) -> MCPClientProtocol:
        if self._client_factory is not None:
            return self._client_factory(server)
        return StdioMCPClient(server=server)

    @staticmethod
    def _load_settings(*, project_root: str | Path | None) -> RuntimeSettings:
        try:
            return load_runtime_settings(project_root)
        except ValueError:
            root = discover_project_root(project_root)
            pyproject_data = load_pyproject(root / "pyproject.toml")
            return RuntimeSettings(
                project_root=root,
                llm=LLMSettings(),
                active_profile_name=None,
                llm_profiles={},
                mcp_servers=parse_mcp_servers(pyproject_data),
            )


AsyncResultT = TypeVar("AsyncResultT")


class StdioMCPClient:
    def __init__(self, *, server: MCPServerSettings) -> None:
        self._server = server

    def list_tools(self) -> list[dict[str, object]]:
        tools = self._run_async_operation(self._list_tools)
        return [
            {
                "server_name": self._server.name,
                "tool_name": tool["name"],
                "namespace": self._server.name,
                "transport": self._server.transport_type,
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in tools
        ]

    def call_tool(self, *, tool_name: str, arguments: dict[str, object]) -> ToolExecutionResult:
        payload = self._run_async_operation(
            lambda: self._call_tool(tool_name=tool_name, arguments=arguments)
        )
        text = "\n".join(payload["texts"]).strip()
        data = payload["structured"]
        return ToolExecutionResult(
            status="success",
            text=text,
            data=data if isinstance(data, dict) else None,
            execution_meta={
                "transport": self._server.transport_type,
                "structured_content": data,
            },
        )

    def _run_async_operation(
        self,
        operation: Callable[[], Awaitable[AsyncResultT]],
    ) -> AsyncResultT:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(operation())

        future: Future[AsyncResultT] = Future()

        def runner() -> None:
            try:
                result = asyncio.run(operation())
            except Exception as exc:
                future.set_exception(exc)
                return
            future.set_result(result)

        thread = threading.Thread(
            target=runner,
            name=f"mcp-stdio-{self._server.name}",
            daemon=True,
        )
        thread.start()
        return future.result()

    async def _list_tools(self) -> list[dict[str, object]]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=self._server.command,
            args=self._server.args,
            env=self._server.env or None,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools: list[dict[str, object]] = []
                for tool in result.tools:
                    tools.append(
                        {
                            "name": getattr(tool, "name", ""),
                            "description": getattr(tool, "description", "") or "",
                            "input_schema": getattr(tool, "inputSchema", {}) or {},
                        }
                    )
                return tools

    async def _call_tool(self, *, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=self._server.command,
            args=self._server.args,
            env=self._server.env or None,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments=arguments),
                    timeout=self._server.tool_timeout_sec,
                )
                texts: list[str] = []
                for content in getattr(result, "content", []):
                    if getattr(content, "type", None) == "text":
                        text = getattr(content, "text", None)
                        if isinstance(text, str):
                            texts.append(text)
                return {
                    "texts": texts,
                    "structured": getattr(result, "structuredContent", None),
                }
