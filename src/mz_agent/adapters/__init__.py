"""MzAgent 第一阶段适配层。"""

from .llm import LLMAdapter
from .mcp import MCPAdapter
from .rag import RAGAdapter
from .skill import SkillAdapter
from .tool import ToolAdapter

from ..contracts.action import NextAction
from ..contracts.context import ExecutionContext
from ..contracts.llm import LLMMessage, LLMRequest
from ..contracts.tooling import ToolCallerContext, ToolExecutionPolicy, ToolExecutionRequest

__all__ = [
    "AdapterHub",
    "LLMAdapter",
    "MCPAdapter",
    "RAGAdapter",
    "SkillAdapter",
    "ToolAdapter",
]


class AdapterHub:
    def __init__(
        self,
        *,
        tool: ToolAdapter | None = None,
        mcp: MCPAdapter | None = None,
        llm: LLMAdapter | None = None,
        rag: RAGAdapter | None = None,
        skill: SkillAdapter | None = None,
    ) -> None:
        self.tool = tool or ToolAdapter()
        self.mcp = mcp or MCPAdapter()
        self.llm = llm or LLMAdapter()
        self.rag = rag or RAGAdapter()
        self.skill = skill or SkillAdapter()

    def dispatch(
        self,
        *,
        action: NextAction,
        execution_context: ExecutionContext,
    ) -> dict[str, object]:
        if action.action_type == "tool":
            result = self.tool.execute(
                request=ToolExecutionRequest(
                    request_id=execution_context.request_id,
                    session_id=execution_context.session_id,
                    tool_name=action.action_target or "",
                    arguments=_extract_arguments(action=action),
                    execution_policy=ToolExecutionPolicy(idempotent=False),
                    caller_context=ToolCallerContext(
                        source="react",
                        trace_id=execution_context.trace_id,
                    ),
                )
            )
            return {
                "source": "tool",
                "result": result.model_dump(mode="json"),
            }

        if action.action_type == "mcp":
            result = self.mcp.invoke(
                server_name=_split_target(action.action_target)[0],
                tool_name=_split_target(action.action_target)[1],
                arguments=_extract_arguments(action=action),
                execution_context=execution_context,
            )
            return {
                "source": "mcp",
                "result": result.model_dump(mode="json"),
            }

        if action.action_type == "llm":
            action_input = action.action_input
            raw_tool_schemas = action_input.get("tool_schemas", [])
            raw_response_schema = action_input.get("response_schema")
            raw_route_hint = action_input.get("route_hint")
            raw_profile_name = action_input.get("profile_name")
            raw_timeout = action_input.get("timeout")
            raw_stream = action_input.get("stream")
            request = LLMRequest(
                messages=[
                    message
                    if isinstance(message, LLMMessage)
                    else LLMMessage.model_validate(message)
                    for message in action_input.get(
                        "messages",
                        [{"role": "user", "content": ""}],
                    )
                ],
                model_policy=str(action_input.get("model_policy", "quality")),
                profile_name=(
                    raw_profile_name if isinstance(raw_profile_name, str) and raw_profile_name else None
                ),
                route_hint=raw_route_hint if isinstance(raw_route_hint, str) else None,
                tool_schemas=raw_tool_schemas if isinstance(raw_tool_schemas, list) else [],
                response_schema=(
                    raw_response_schema if isinstance(raw_response_schema, dict) else None
                ),
                stream=bool(raw_stream) if isinstance(raw_stream, bool) else False,
                timeout=raw_timeout if isinstance(raw_timeout, int) else 30_000,
            )
            response = self.llm.respond(
                request=request,
                execution_context=execution_context,
            )
            return {
                "source": "llm",
                "response": response.model_dump(mode="json"),
            }

        if action.action_type == "rag":
            result = self.rag.retrieve(
                query=str(action.action_input.get("query", "")),
                execution_context=execution_context,
            )
            return {
                "source": "rag",
                "result": result,
            }

        if action.action_type == "skill":
            result = self.skill.consume(
                name=action.action_target or "",
                skill_args=action.action_input,
            )
            return {
                "source": "skill",
                "result": result,
            }

        return {
            "source": "react",
            "result": {},
        }


def _extract_arguments(*, action: NextAction) -> dict[str, object]:
    raw_arguments = action.action_input.get("arguments")
    if isinstance(raw_arguments, dict):
        return raw_arguments
    return {}


def _split_target(target: str | None) -> tuple[str, str]:
    if target is None:
        return ("default", "")
    if ":" not in target:
        return ("default", target)
    server_name, tool_name = target.split(":", 1)
    return (server_name, tool_name)
