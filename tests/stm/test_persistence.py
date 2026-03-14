from pathlib import Path

from mz_agent.adapters import AdapterHub, ToolAdapter
from mz_agent.cli import _prepare_snapshot_for_round
from mz_agent.contracts.action import AvailableAction
from mz_agent.contracts.context import ContextSnapshot, ExecutionContext
from mz_agent.contracts.tooling import ToolDefinition
from mz_agent.orchestration import FileBackedSTM, Pipeline
from mz_agent.contracts.state import ReactStatus
from mz_agent.runtime.writeback import WritebackRecord


def test_file_backed_stm_persists_snapshot_and_writeback(tmp_path: Path) -> None:
    storage_path = tmp_path / "stm.json"
    stm = FileBackedSTM(storage_path=storage_path)

    stm.replace_context_snapshot(
        snapshot=ContextSnapshot(
            current_plan=None,
            stm={"round": 1},
        )
    )
    updated = stm.apply_writeback(
        record=WritebackRecord(
            stage="post_answer",
            react_status=ReactStatus.FINISHED,
            execution_context={
                "request_id": "req_001",
                "session_id": "sess_001",
                "plan_id": None,
                "trace_id": "trace_001",
                "source": "react",
            },
            current_step=None,
            observation={"draft_answer": "完成"},
            final_answer="完成",
            metadata={},
        )
    )

    reloaded = FileBackedSTM(storage_path=storage_path)

    assert storage_path.exists()
    assert updated.stm["last_react_status"] == "finished"
    assert reloaded.latest_context_snapshot().stm["last_final_answer"] == "完成"
    assert reloaded.last_writeback() is not None
    assert reloaded.last_writeback().final_answer == "完成"


def test_file_backed_stm_records_repl_conversation_history_for_llm_and_tool(
    tmp_path: Path,
) -> None:
    storage_path = tmp_path / "stm.json"
    stm = FileBackedSTM(storage_path=storage_path)
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
            handler=lambda query="": {"text": f"已执行搜索：{query}", "data": {"query": query}},
        )
    )
    pipeline = Pipeline(stm=stm, adapters=AdapterHub(tool=tool_adapter))

    llm_snapshot = _prepare_snapshot_for_round(
        snapshot=ContextSnapshot(current_plan=None),
        goal="你好",
        action_type="llm",
        target=None,
        draft_answer="任务已收束",
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    llm_result = pipeline.run_round(
        goal="你好",
        context_snapshot=llm_snapshot,
        available_actions=[AvailableAction(action_type="llm", targets=[], availability="available")],
        execution_context=execution_context,
    )

    tool_snapshot = _prepare_snapshot_for_round(
        snapshot=llm_result.context_snapshot,
        goal="搜索协议",
        action_type="tool",
        target="search_docs",
        draft_answer="任务已收束",
    )
    tool_result = pipeline.run_round(
        goal="搜索协议",
        context_snapshot=tool_snapshot,
        available_actions=[
            AvailableAction(
                action_type="tool",
                targets=["search_docs"],
                availability="available",
            )
        ],
        execution_context=ExecutionContext(
            request_id="req_002",
            session_id="sess_001",
            plan_id=None,
            trace_id="trace_002",
            source="react",
        ),
    )

    history = tool_result.context_snapshot.perception["conversation_messages"]
    assert history[0] == {"role": "user", "content": "你好"}
    assert history[1] == {"role": "assistant", "content": "你好"}
    assert history[2] == {"role": "user", "content": "搜索协议"}
    assert history[3]["role"] == "assistant"
    assert "已执行搜索：搜索协议" in history[3]["content"]
    assert "pending_user_message" not in tool_result.context_snapshot.perception
