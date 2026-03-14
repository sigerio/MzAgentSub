"""MzAgent 命令行入口。"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from uuid import uuid4

from .adapters import AdapterHub, LLMAdapter, MCPAdapter, ToolAdapter
from .contracts.action import AvailableAction
from .contracts.context import ContextSnapshot, ExecutionContext
from .contracts.tooling import ToolDefinition
from .orchestration import FileBackedSTM, Pipeline, PipelineRoundResult


@dataclass
class ReplState:
    mode: str
    target: str | None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 MzAgent 单轮主链或最小 REPL。")
    parser.add_argument("--goal", help="本轮目标。")
    parser.add_argument(
        "--action-type",
        choices=["tool", "finish", "llm", "rag", "skill", "mcp", "clarify"],
        help="动作类型。",
    )
    parser.add_argument("--target", default=None, help="动作目标。")
    parser.add_argument(
        "--stm-path",
        default=".mz_agent/stm_state.json",
        help="STM 持久化文件路径。",
    )
    parser.add_argument("--live-llm", action="store_true", help="启用真实 LLM 调用。")
    parser.add_argument(
        "--draft-answer",
        default="任务已收束",
        help="当 action-type=finish 时使用的草稿答复。",
    )
    parser.add_argument("--repl", action="store_true", help="启动最小交互式对话模式。")
    parser.add_argument(
        "--session-id",
        default="sess_cli",
        help="会话标识，用于 REPL 或单轮命令的上下文区分。",
    )
    parser.add_argument(
        "--request-prefix",
        default="req_cli",
        help="请求标识前缀。",
    )
    parser.add_argument(
        "--trace-prefix",
        default="trace_cli",
        help="追踪标识前缀。",
    )
    args = parser.parse_args(argv)
    _validate_args(args=args, parser=parser)
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[2]
    pipeline, stm = _build_runtime(args=args, project_root=project_root)

    if args.repl:
        _run_repl(args=args, pipeline=pipeline, stm=stm)
        return

    result = _run_single_round(
        args=args,
        pipeline=pipeline,
        stm=stm,
        goal=args.goal or "",
        action_type=args.action_type or "llm",
        target=args.target,
    )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


def _validate_args(*, args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.repl:
        if args.action_type is None:
            args.action_type = "llm"
        return
    if not args.goal:
        parser.error("非 REPL 模式必须提供 --goal。")
    if args.action_type is None:
        parser.error("非 REPL 模式必须提供 --action-type。")


def _build_runtime(*, args: argparse.Namespace, project_root: Path) -> tuple[Pipeline, FileBackedSTM]:
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
            handler=lambda query="": {
                "text": f"已执行搜索：{query}" if query else "已执行搜索",
                "data": {"hits": 1, "query": query},
            },
        )
    )

    adapters = AdapterHub(
        tool=tool_adapter,
        llm=LLMAdapter(project_root=project_root, live_mode=args.live_llm),
        mcp=MCPAdapter(project_root=project_root),
    )
    stm = FileBackedSTM(storage_path=project_root / args.stm_path)
    pipeline = Pipeline(adapters=adapters, stm=stm)
    return pipeline, stm


def _run_single_round(
    *,
    args: argparse.Namespace,
    pipeline: Pipeline,
    stm: FileBackedSTM,
    goal: str,
    action_type: str,
    target: str | None,
) -> PipelineRoundResult:
    snapshot = stm.latest_context_snapshot()
    snapshot = _prepare_snapshot_for_round(
        snapshot=snapshot,
        goal=goal,
        action_type=action_type,
        target=target,
        draft_answer=args.draft_answer,
    )

    request_id, trace_id = _build_request_identifiers(
        request_prefix=args.request_prefix,
        trace_prefix=args.trace_prefix,
        action_type=action_type,
    )
    execution_context = ExecutionContext(
        request_id=request_id,
        session_id=args.session_id,
        plan_id=snapshot.current_plan.plan_id if snapshot.current_plan is not None else None,
        trace_id=trace_id,
        source="react",
    )

    return pipeline.run_round(
        goal=goal,
        context_snapshot=snapshot,
        available_actions=[
            AvailableAction(
                action_type=action_type,
                targets=[target] if target else [],
                availability="available",
            )
        ],
        execution_context=execution_context,
    )


def _run_repl(
    *,
    args: argparse.Namespace,
    pipeline: Pipeline,
    stm: FileBackedSTM,
) -> None:
    state = ReplState(mode=args.action_type or "llm", target=args.target)
    print(
        "MzAgent 最小 REPL 已启动。输入内容后回车发送，输入 /help 查看命令，输入 /exit 退出。"
    )
    while True:
        try:
            user_input = input("mz-agent> ").strip()
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print("\n已中断，输入 /exit 退出。")
            continue

        if not user_input:
            continue

        if user_input.startswith("/"):
            control = _handle_repl_command(command=user_input, stm=stm, state=state)
            if control == "exit":
                break
            if control is not None:
                print(control)
            continue

        result = _run_single_round(
            args=args,
            pipeline=pipeline,
            stm=stm,
            goal=user_input,
            action_type=state.mode,
            target=state.target,
        )
        print(_render_round_result(result=result))


def _handle_repl_command(*, command: str, stm: FileBackedSTM, state: ReplState) -> str | None:
    if command in {"/exit", "/quit"}:
        return "exit"
    if command == "/help":
        return "\n".join(
            [
                "可用命令：",
                "/help                 查看命令",
                "/exit                 退出 REPL",
                "/quit                 退出 REPL",
                "/reset                清空当前会话上下文",
                "/history              查看当前对话历史",
                "/status               查看当前模式与目标",
                "/mode <动作类型>      切换模式，如 /mode llm 或 /mode mcp",
                "/target <动作目标>    设置目标，如 /target cunzhi:zhi",
            ]
        )
    if command == "/reset":
        stm.replace_context_snapshot(snapshot=ContextSnapshot(current_plan=None))
        return "当前会话上下文已清空。"
    if command == "/history":
        snapshot = stm.latest_context_snapshot()
        history = snapshot.perception.get("conversation_messages", [])
        if not isinstance(history, list) or not history:
            return "当前没有对话历史。"
        lines: list[str] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if isinstance(role, str) and isinstance(content, str):
                lines.append(f"[{role}] {content}")
        return "\n".join(lines) if lines else "当前没有对话历史。"
    if command == "/status":
        return f"当前模式：{state.mode}\n当前目标：{state.target or 'N/A'}"
    if command.startswith("/mode "):
        mode = command.split(" ", 1)[1].strip()
        if mode not in {"tool", "finish", "llm", "rag", "skill", "mcp", "clarify"}:
            return "未知模式，可选值：tool/finish/llm/rag/skill/mcp/clarify"
        state.mode = mode
        if mode == "llm":
            state.target = None
        return f"已切换模式：{state.mode}"
    if command.startswith("/target "):
        target = command.split(" ", 1)[1].strip()
        state.target = target or None
        return f"已设置目标：{state.target or 'N/A'}"
    return "未知命令，输入 /help 查看可用命令。"


def _prepare_snapshot_for_round(
    *,
    snapshot: ContextSnapshot,
    goal: str,
    action_type: str,
    target: str | None,
    draft_answer: str,
) -> ContextSnapshot:
    perception = dict(snapshot.perception)
    perception.update(
        _build_perception_payload(
            goal=goal,
            action_type=action_type,
            target=target,
        )
    )

    pending_action_arguments = _build_pending_action_arguments(
        action_type=action_type,
        target=target,
        goal=goal,
    )
    if pending_action_arguments is not None:
        perception["pending_action_arguments"] = pending_action_arguments
    else:
        perception.pop("pending_action_arguments", None)

    update: dict[str, object] = {"perception": perception}
    if action_type == "finish" and snapshot.last_observation is None:
        update["last_observation"] = {"draft_answer": draft_answer}
    return snapshot.model_copy(update=update)


def _build_perception_payload(
    *,
    goal: str,
    action_type: str,
    target: str | None,
) -> dict[str, object]:
    normalized_goal = _normalize_goal(goal=goal)
    constraints = _extract_constraints(goal=normalized_goal)
    intent_summary = _extract_intent_summary(
        goal=normalized_goal,
        constraints=constraints,
    )
    clarify_needed, clarify_reason = _judge_clarify_needed(
        normalized_goal=normalized_goal,
        action_type=action_type,
        target=target,
        intent_summary=intent_summary,
    )
    perception: dict[str, object] = {
        "pending_user_message": goal,
        "normalized_goal": normalized_goal,
        "intent_summary": intent_summary,
        "constraints": constraints,
        "clarify_needed": clarify_needed,
    }
    if clarify_reason is not None:
        perception["clarify_reason"] = clarify_reason
    else:
        perception.pop("clarify_reason", None)
    return perception


def _build_pending_action_arguments(
    *,
    action_type: str,
    target: str | None,
    goal: str,
) -> dict[str, object] | None:
    if action_type == "mcp" and target == "cunzhi:zhi":
        return {"message": goal, "is_markdown": True}
    if action_type == "tool" and target == "search_docs":
        return {"query": goal}
    if action_type in {"tool", "mcp"}:
        return {}
    return None


def _normalize_goal(*, goal: str) -> str:
    return " ".join(goal.strip().split())


def _extract_constraints(*, goal: str) -> list[str]:
    if not goal:
        return []
    segments = [
        segment.strip()
        for segment in re.split(r"[，,。；;\n]+", goal)
        if segment.strip()
    ]
    return [
        segment
        for segment in segments
        if any(keyword in segment for keyword in ("只", "必须", "不要", "不能", "限定", "仅"))
    ]


def _extract_intent_summary(*, goal: str, constraints: list[str]) -> str:
    if not goal:
        return ""
    segments = [
        segment.strip()
        for segment in re.split(r"[，,。；;\n]+", goal)
        if segment.strip()
    ]
    intent_segments = [segment for segment in segments if segment not in constraints]
    if not intent_segments:
        return goal
    return "；".join(intent_segments)


def _judge_clarify_needed(
    *,
    normalized_goal: str,
    action_type: str,
    target: str | None,
    intent_summary: str,
) -> tuple[bool, str | None]:
    if not normalized_goal:
        return (True, "目标为空。")
    if action_type in {"tool", "mcp", "skill", "rag"} and not target:
        return (True, "缺少动作目标。")
    vague_goals = {"处理一下", "看一下", "搞一下", "弄一下", "帮我处理一下", "帮我看一下"}
    if normalized_goal in vague_goals and not intent_summary:
        return (True, "缺少明确意图。")
    return (False, None)


def _build_request_identifiers(
    *,
    request_prefix: str,
    trace_prefix: str,
    action_type: str,
) -> tuple[str, str]:
    token = uuid4().hex[:8]
    return (
        f"{request_prefix}.{token}",
        f"{trace_prefix}.{action_type}.{token}",
    )


def _render_round_result(*, result: PipelineRoundResult) -> str:
    if result.output_text:
        return result.output_text

    observation = result.observation or {}
    source = observation.get("source")

    if source == "llm":
        response = observation.get("response")
        if isinstance(response, dict):
            text = _extract_text_from_llm_response(response=response)
            if text:
                return text
        return "LLM 已返回结果，但未提取到文本。"

    if source in {"tool", "mcp"}:
        result_payload = observation.get("result")
        if isinstance(result_payload, dict):
            text = result_payload.get("text")
            if isinstance(text, str) and text:
                return text
            return json.dumps(result_payload, ensure_ascii=False, indent=2)

    if source == "rag":
        result_payload = observation.get("result")
        return json.dumps(result_payload, ensure_ascii=False, indent=2)

    if source == "skill":
        result_payload = observation.get("result")
        return json.dumps(result_payload, ensure_ascii=False, indent=2)

    final_answer = result.react_result.final_answer
    if isinstance(final_answer, str) and final_answer:
        return final_answer

    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _extract_text_from_llm_response(*, response: dict[str, object]) -> str:
    blocks = response.get("content_blocks", [])
    if not isinstance(blocks, list):
        return ""

    texts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        content = block.get("content")
        if isinstance(content, str) and content:
            texts.append(content)
    return "\n".join(texts)


if __name__ == "__main__":
    main()
