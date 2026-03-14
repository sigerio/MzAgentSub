from mz_agent.cli import _build_pending_action_arguments, _prepare_snapshot_for_round
from mz_agent.contracts.context import ContextSnapshot


def test_prepare_snapshot_for_tool_round_records_pending_message_and_query() -> None:
    snapshot = _prepare_snapshot_for_round(
        snapshot=ContextSnapshot(current_plan=None),
        goal="搜索协议",
        action_type="tool",
        target="search_docs",
        draft_answer="任务已收束",
    )

    assert snapshot.perception["pending_user_message"] == "搜索协议"
    assert snapshot.perception["pending_action_arguments"] == {"query": "搜索协议"}
    assert snapshot.last_observation is None


def test_prepare_snapshot_for_finish_round_uses_default_draft_answer_once() -> None:
    snapshot = _prepare_snapshot_for_round(
        snapshot=ContextSnapshot(current_plan=None),
        goal="整理结果",
        action_type="finish",
        target=None,
        draft_answer="任务已收束",
    )

    assert snapshot.last_observation == {"draft_answer": "任务已收束"}
    assert "pending_action_arguments" not in snapshot.perception


def test_prepare_snapshot_for_finish_round_does_not_overwrite_existing_answer() -> None:
    snapshot = _prepare_snapshot_for_round(
        snapshot=ContextSnapshot(
            current_plan=None,
            last_observation={"draft_answer": "已有草稿"},
        ),
        goal="整理结果",
        action_type="finish",
        target=None,
        draft_answer="任务已收束",
    )

    assert snapshot.last_observation == {"draft_answer": "已有草稿"}


def test_build_pending_action_arguments_only_exposes_frozen_bridges() -> None:
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
    assert _build_pending_action_arguments(
        action_type="mcp",
        target="cunzhi:other",
        goal="协议",
    ) == {}
    assert _build_pending_action_arguments(
        action_type="llm",
        target=None,
        goal="协议",
    ) is None
