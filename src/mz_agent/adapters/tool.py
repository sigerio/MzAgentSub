"""MzAgent 第一阶段 Tool 适配壳。"""

from __future__ import annotations

from typing import cast

from ..contracts.tooling import ToolDefinition, ToolExecutionRequest, ToolExecutionResult


class ToolAdapter:
    def __init__(self) -> None:
        self._definitions: dict[str, ToolDefinition] = {}

    def register(self, *, definition: ToolDefinition) -> None:
        self._definitions[definition.name] = definition

    def execute(self, *, request: ToolExecutionRequest) -> ToolExecutionResult:
        definition = self._definitions.get(request.tool_name)
        if definition is None:
            return ToolExecutionResult(
                status="error",
                text="",
                error_code="TOL_001",
                message="工具不存在。",
                execution_meta={"tool_name": request.tool_name},
            )

        missing_fields = self._missing_required_fields(
            schema=definition.input_schema,
            arguments=request.arguments,
        )
        if missing_fields:
            return ToolExecutionResult(
                status="error",
                text="",
                error_code="TOL_002",
                message=f"参数校验失败：缺少 {', '.join(missing_fields)}。",
                execution_meta={"tool_name": request.tool_name},
                result_schema_version=definition.result_schema_version,
            )

        if request.execution_policy.dry_run:
            return ToolExecutionResult(
                status="success",
                text="已完成模拟执行。",
                data={"arguments": request.arguments},
                execution_meta={"dry_run": True},
                result_schema_version=definition.result_schema_version,
            )

        try:
            raw_result = definition.handler(**request.arguments)
        except Exception as exc:
            return ToolExecutionResult(
                status="error",
                text="",
                error_code="TOL_003",
                message=f"工具执行异常：{exc}",
                execution_meta={"tool_name": request.tool_name},
                result_schema_version=definition.result_schema_version,
            )

        return self._normalize_result(
            raw_result=raw_result,
            result_schema_version=definition.result_schema_version,
        )

    @staticmethod
    def _missing_required_fields(
        *,
        schema: dict[str, object],
        arguments: dict[str, object],
    ) -> list[str]:
        required = schema.get("required")
        if not isinstance(required, list):
            return []
        return [str(field) for field in required if field not in arguments]

    @staticmethod
    def _normalize_result(
        *,
        raw_result: object,
        result_schema_version: str,
    ) -> ToolExecutionResult:
        if isinstance(raw_result, ToolExecutionResult):
            return raw_result
        if isinstance(raw_result, str):
            return ToolExecutionResult(
                status="success",
                text=raw_result,
                result_schema_version=result_schema_version,
            )
        if isinstance(raw_result, dict):
            text = raw_result.get("text")
            data = raw_result.get("data")
            message = raw_result.get("message")
            execution_meta = raw_result.get("execution_meta")
            return ToolExecutionResult(
                status=cast(str, raw_result.get("status", "success")),
                text=text if isinstance(text, str) else "",
                data=data if isinstance(data, dict) else None,
                message=message if isinstance(message, str) else None,
                execution_meta=execution_meta if isinstance(execution_meta, dict) else {},
                result_schema_version=result_schema_version,
            )
        return ToolExecutionResult(
            status="success",
            text=str(raw_result),
            result_schema_version=result_schema_version,
        )

