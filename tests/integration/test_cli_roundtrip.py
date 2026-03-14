from pathlib import Path
from types import SimpleNamespace

from mz_agent.cli import _build_runtime, _run_single_round
from mz_agent.orchestration import FileBackedSTM


def test_cli_single_round_runs_through_runtime_and_persists_stm(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n',
        encoding="utf-8",
    )
    args = SimpleNamespace(
        live_llm=False,
        stm_path=".mz_agent/test_stm.json",
        draft_answer="任务已收束",
        request_prefix="req_cli",
        trace_prefix="trace_cli",
        session_id="sess_cli",
    )

    pipeline, stm = _build_runtime(args=args, project_root=tmp_path)
    result = _run_single_round(
        args=args,
        pipeline=pipeline,
        stm=stm,
        goal="搜索协议",
        action_type="tool",
        target="search_docs",
    )

    storage_path = tmp_path / ".mz_agent" / "test_stm.json"
    reloaded = FileBackedSTM(storage_path=storage_path)

    assert result.observation == {
        "source": "tool",
        "result": {
            "status": "success",
            "text": "已执行搜索：搜索协议",
            "data": {"hits": 1, "query": "搜索协议"},
            "error_code": None,
            "message": None,
            "result_schema_version": "v1",
            "execution_meta": {},
        },
    }
    assert storage_path.exists()
    history = reloaded.latest_context_snapshot().perception["conversation_messages"]
    assert history[0] == {"role": "user", "content": "搜索协议"}
    assert "已执行搜索：搜索协议" in history[1]["content"]
