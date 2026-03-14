#!/usr/bin/env python3
"""MzAgent 第一阶段单轮主链演示脚本。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mz_agent.adapters import AdapterHub, ToolAdapter  # noqa: E402
from mz_agent.contracts.action import AvailableAction  # noqa: E402
from mz_agent.contracts.context import ContextSnapshot, ExecutionContext  # noqa: E402
from mz_agent.contracts.tooling import ToolDefinition  # noqa: E402
from mz_agent.orchestration import Pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="演示 MzAgent 单轮主链。")
    parser.add_argument("--goal", required=True, help="当前轮目标。")
    parser.add_argument(
        "--action-type",
        required=True,
        choices=["tool", "finish", "llm", "rag", "skill", "mcp", "clarify"],
        help="演示动作类型。",
    )
    parser.add_argument("--target", default=None, help="动作目标名称。")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    tool_adapter = ToolAdapter()
    tool_adapter.register(
        definition=ToolDefinition(
            name="search_docs",
            description="搜索文档",
            input_schema={"type": "object", "required": []},
            permission_domain="docs",
            risk_level="low",
            idempotent=True,
            requires_confirmation=False,
            handler=lambda: {"text": "已执行搜索", "data": {"hits": 1}},
        )
    )

    pipeline = Pipeline(adapters=AdapterHub(tool=tool_adapter))
    snapshot = ContextSnapshot(
        current_plan=None,
        last_observation={"draft_answer": "任务已收束"} if args.action_type == "finish" else None,
    )
    execution_context = ExecutionContext(
        request_id="req_demo",
        session_id="sess_demo",
        plan_id=None,
        trace_id="trace_demo",
        source="react",
    )

    available_action = AvailableAction(
        action_type=args.action_type,
        targets=[args.target] if args.target else [],
        availability="available",
    )

    result = pipeline.run_round(
        goal=args.goal,
        context_snapshot=snapshot,
        available_actions=[available_action],
        execution_context=execution_context,
    )

    print(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

