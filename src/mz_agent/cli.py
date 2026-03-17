"""MzAgent 命令行入口。"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .app.runtime import (
    RuntimeOptions,
    build_pending_action_arguments,
    build_perception_payload,
    build_request_identifiers,
    build_runtime,
    extract_constraints,
    extract_intent_summary,
    extract_text_from_llm_response,
    judge_clarify_needed,
    normalize_goal,
    prepare_snapshot_for_round,
    render_round_result,
    run_single_round,
)
from .contracts.context import ContextSnapshot
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
    parser.add_argument(
        "--llm-profile",
        default="",
        help="默认使用的 LLM 配置方案名称。",
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
    return build_runtime(
        options=RuntimeOptions.from_namespace(args),
        project_root=project_root,
    )


def _run_single_round(
    *,
    args: argparse.Namespace,
    pipeline: Pipeline,
    stm: FileBackedSTM,
    goal: str,
    action_type: str,
    target: str | None,
) -> PipelineRoundResult:
    return run_single_round(
        options=RuntimeOptions.from_namespace(args),
        pipeline=pipeline,
        stm=stm,
        goal=goal,
        action_type=action_type,
        target=target,
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
    profile_name: str | None = None,
    draft_answer: str,
) -> ContextSnapshot:
    return prepare_snapshot_for_round(
        snapshot=snapshot,
        goal=goal,
        action_type=action_type,
        target=target,
        profile_name=profile_name,
        draft_answer=draft_answer,
    )


def _build_perception_payload(
    *,
    goal: str,
    action_type: str,
    target: str | None,
) -> dict[str, object]:
    return build_perception_payload(
        goal=goal,
        action_type=action_type,
        target=target,
    )


def _build_pending_action_arguments(
    *,
    action_type: str,
    target: str | None,
    goal: str,
    profile_name: str | None = None,
) -> dict[str, object] | None:
    return build_pending_action_arguments(
        action_type=action_type,
        target=target,
        goal=goal,
        profile_name=profile_name,
    )


def _normalize_goal(*, goal: str) -> str:
    return normalize_goal(goal=goal)


def _extract_constraints(*, goal: str) -> list[str]:
    return extract_constraints(goal=goal)


def _extract_intent_summary(*, goal: str, constraints: list[str]) -> str:
    return extract_intent_summary(goal=goal, constraints=constraints)


def _judge_clarify_needed(
    *,
    normalized_goal: str,
    action_type: str,
    target: str | None,
    intent_summary: str,
) -> tuple[bool, str | None]:
    return judge_clarify_needed(
        normalized_goal=normalized_goal,
        action_type=action_type,
        target=target,
        intent_summary=intent_summary,
    )


def _build_request_identifiers(
    *,
    request_prefix: str,
    trace_prefix: str,
    action_type: str,
) -> tuple[str, str]:
    return build_request_identifiers(
        request_prefix=request_prefix,
        trace_prefix=trace_prefix,
        action_type=action_type,
    )


def _render_round_result(*, result: PipelineRoundResult) -> str:
    return render_round_result(result=result)


def _extract_text_from_llm_response(*, response: dict[str, object]) -> str:
    return extract_text_from_llm_response(response=response)


if __name__ == "__main__":
    main()
