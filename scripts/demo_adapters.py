#!/usr/bin/env python3
"""MzAgent 第一阶段适配层演示脚本。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mz_agent.adapters.llm import LLMAdapter  # noqa: E402
from mz_agent.adapters.mcp import MCPAdapter  # noqa: E402
from mz_agent.adapters.rag import RAGAdapter  # noqa: E402
from mz_agent.adapters.skill import SkillAdapter, SkillDescriptor  # noqa: E402
from mz_agent.adapters.tool import ToolAdapter  # noqa: E402
from mz_agent.contracts.context import ExecutionContext  # noqa: E402
from mz_agent.knowledge import KnowledgeBase  # noqa: E402
from mz_agent.contracts.llm import LLMMessage, LLMRequest  # noqa: E402
from mz_agent.contracts.tooling import (  # noqa: E402
    MCPBinding,
    ToolCallerContext,
    ToolDefinition,
    ToolExecutionPolicy,
    ToolExecutionRequest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="演示 MzAgent 适配层。")
    parser.add_argument(
        "--adapter",
        required=True,
        choices=["tool", "mcp", "llm", "rag", "skill"],
        help="要演示的适配器。",
    )
    parser.add_argument("--live", action="store_true", help="启用真实配置联调。")
    parser.add_argument("--server", default="cunzhi", help="MCP 服务名。")
    parser.add_argument("--tool", default="", help="MCP 工具名。")
    parser.add_argument("--arguments", default="{}", help="MCP 工具参数 JSON。")
    parser.add_argument("--prompt", default="你好，请简要介绍自己。", help="LLM 提示词。")
    parser.add_argument(
        "--list-capabilities",
        action="store_true",
        help="列出 MCP 服务能力，而不是直接调用工具。",
    )
    return parser.parse_args()


def build_execution_context() -> ExecutionContext:
    return ExecutionContext(
        request_id="req_demo",
        session_id="sess_demo",
        plan_id=None,
        trace_id="trace_demo",
        source="react",
    )


def main() -> None:
    args = parse_args()
    execution_context = build_execution_context()

    if args.adapter == "tool":
        adapter = ToolAdapter()
        adapter.register(
            definition=ToolDefinition(
                name="echo",
                description="回显工具",
                input_schema={"type": "object", "required": ["query"]},
                permission_domain="general",
                risk_level="low",
                idempotent=True,
                requires_confirmation=False,
                handler=lambda query: {"text": f"收到：{query}", "data": {"query": query}},
            )
        )
        result = adapter.execute(
            request=ToolExecutionRequest(
                request_id="req_demo",
                session_id="sess_demo",
                tool_name="echo",
                arguments={"query": "hello"},
                execution_policy=ToolExecutionPolicy(idempotent=True),
                caller_context=ToolCallerContext(source="react", trace_id="trace_demo"),
            )
        )
        payload = result.model_dump(mode="json")
    elif args.adapter == "mcp":
        adapter = MCPAdapter(project_root=ROOT)
        if args.live:
            if args.list_capabilities:
                payload = adapter.list_capabilities(server_name=args.server)
            else:
                payload = adapter.invoke(
                    server_name=args.server,
                    tool_name=args.tool,
                    arguments=json.loads(args.arguments),
                    execution_context=execution_context,
                ).model_dump(mode="json")
        else:
            adapter.register(
                binding=MCPBinding(
                    server_name="docs",
                    transport="stdio",
                    tool_name="search",
                    namespace="docs",
                ),
                handler=lambda query: {"text": f"命中：{query}", "data": {"query": query}},
            )
            payload = adapter.invoke(
                server_name="docs",
                tool_name="search",
                arguments={"query": "协议"},
                execution_context=execution_context,
            ).model_dump(mode="json")
    elif args.adapter == "llm":
        adapter = LLMAdapter(project_root=ROOT, live_mode=args.live)
        payload = adapter.respond(
            request=LLMRequest(
                messages=[LLMMessage(role="user", content=args.prompt)],
                model_policy="quality",
                route_hint=None if args.live else "openai-mini",
            ),
            execution_context=execution_context,
        ).model_dump(mode="json")
    elif args.adapter == "rag":
        knowledge_base = KnowledgeBase()
        knowledge_base.ingest_text(
            document_id="protocol",
            title="protocol",
            source_path="memory://protocol",
            content="协议冻结总表\n\n协议状态机与字段约束已经冻结。",
        )
        adapter = RAGAdapter(knowledge_base=knowledge_base, top_k=1)
        payload = adapter.retrieve(query="协议", execution_context=execution_context)
    else:
        adapter = SkillAdapter()
        adapter.register(
            skill=SkillDescriptor(
                name="writer",
                description="写作技能",
                prompt="请按要求写作",
            )
        )
        payload = adapter.consume(name="writer")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
