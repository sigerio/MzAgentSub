from pathlib import Path

from mz_agent.cli import (
    ReplState,
    _build_pending_action_arguments,
    _handle_repl_command,
    _prepare_snapshot_for_round,
    _render_round_result,
)
from mz_agent.contracts.action import AvailableAction
from mz_agent.contracts.context import ContextSnapshot, ExecutionContext
from mz_agent.contracts.planning import CurrentPlanRef
from mz_agent.orchestration import FileBackedSTM, Pipeline, ReActEngine, ReActRequest


def test_react_engine_llm_action_carries_conversation_history() -> None:
    engine = ReActEngine()
    snapshot = ContextSnapshot(
        current_plan=None,
        perception={
            "conversation_messages": [
                {"role": "user", "content": "第一句"},
                {"role": "assistant", "content": "第一轮回复"},
            ]
        },
    )

    result = engine.decide(
        request=ReActRequest(
            goal="第二句",
            context_snapshot=snapshot,
            available_actions=[AvailableAction(action_type="llm", targets=[], availability="available")],
        )
    )

    assert result.next_action is not None
    assert result.next_action.action_input["messages"] == [
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第一轮回复"},
        {"role": "user", "content": "第二句"},
    ]


def test_react_engine_mcp_action_carries_bridge_arguments() -> None:
    engine = ReActEngine()
    snapshot = ContextSnapshot(
        current_plan=None,
        perception={
            "pending_user_message": "请审查这段代码",
            "pending_action_arguments": {"message": "请审查这段代码", "is_markdown": True},
        },
    )

    result = engine.decide(
        request=ReActRequest(
            goal="请审查这段代码",
            context_snapshot=snapshot,
            available_actions=[
                AvailableAction(action_type="mcp", targets=["cunzhi:zhi"], availability="available")
            ],
        )
    )

    assert result.next_action is not None
    assert result.next_action.action_target == "cunzhi:zhi"
    assert result.next_action.action_input["arguments"] == {
        "message": "请审查这段代码",
        "is_markdown": True,
    }
def test_repl_commands_and_text_rendering_are_stable(tmp_path: Path) -> None:
    stm = FileBackedSTM(storage_path=tmp_path / "stm.json")
    stm.replace_context_snapshot(
        snapshot=ContextSnapshot(
            current_plan=CurrentPlanRef(plan_id="plan_001", plan_version=1, current_step=None, step_state={}),
            perception={
                "conversation_messages": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "你好，我在。"},
                ]
            },
        )
    )
    state = ReplState(mode="llm", target=None)

    history_output = _handle_repl_command(command="/history", stm=stm, state=state)
    status_output = _handle_repl_command(command="/status", stm=stm, state=state)
    mode_output = _handle_repl_command(command="/mode mcp", stm=stm, state=state)
    target_output = _handle_repl_command(command="/target cunzhi:zhi", stm=stm, state=state)
    reset_output = _handle_repl_command(command="/reset", stm=stm, state=state)
    help_output = _handle_repl_command(command="/help", stm=stm, state=state)

    assert history_output == "[user] 你好\n[assistant] 你好，我在。"
    assert status_output == "当前模式：llm\n当前目标：N/A"
    assert mode_output == "已切换模式：mcp"
    assert target_output == "已设置目标：cunzhi:zhi"
    assert reset_output == "当前会话上下文已清空。"
    assert "可用命令" in (help_output or "")

    pipeline = Pipeline()
    execution_context = ExecutionContext(
        request_id="req_003",
        session_id="sess_002",
        plan_id=None,
        trace_id="trace_003",
        source="react",
    )
    result = pipeline.run_round(
        goal="你好",
        context_snapshot=_prepare_snapshot_for_round(
            snapshot=ContextSnapshot(current_plan=None),
            goal="你好",
            action_type="llm",
            target=None,
            draft_answer="任务已收束",
        ),
        available_actions=[AvailableAction(action_type="llm", targets=[], availability="available")],
        execution_context=execution_context,
    )

    assert _render_round_result(result=result) == "你好"


def test_build_pending_action_arguments_supports_mcp_and_tool() -> None:
    assert _build_pending_action_arguments(
        action_type="mcp",
        target="cunzhi:zhi",
        goal="请审查",
    ) == {"message": "请审查", "is_markdown": True}
    assert _build_pending_action_arguments(
        action_type="tool",
        target="search_docs",
        goal="协议",
    ) == {"query": "协议"}
