from pathlib import Path

from mz_agent.adapters import AdapterHub, RAGAdapter, SkillAdapter
from mz_agent.cli import _prepare_snapshot_for_round
from mz_agent.contracts.action import AvailableAction
from mz_agent.contracts.context import ContextSnapshot, ExecutionContext
from mz_agent.knowledge import KnowledgeBase
from mz_agent.orchestration import FileBackedSTM, Pipeline


def test_pipeline_rag_round_links_perception_knowledge_and_stm(tmp_path: Path) -> None:
    storage_path = tmp_path / ".mz_agent" / "rag_stm.json"
    knowledge_base = KnowledgeBase()
    knowledge_base.ingest_text(
        document_id="protocol",
        title="protocol",
        source_path="memory://protocol",
        content="协议冻结总表\n\n协议状态机与字段约束已经冻结。",
    )
    pipeline = Pipeline(
        adapters=AdapterHub(rag=RAGAdapter(knowledge_base=knowledge_base, top_k=1)),
        stm=FileBackedSTM(storage_path=storage_path),
    )
    snapshot = _prepare_snapshot_for_round(
        snapshot=ContextSnapshot(current_plan=None),
        goal="搜索协议",
        action_type="rag",
        target="knowledge",
        draft_answer="任务已收束",
    )

    result = pipeline.run_round(
        goal="协议",
        context_snapshot=snapshot,
        available_actions=[
            AvailableAction(
                action_type="rag",
                targets=["knowledge"],
                availability="available",
            )
        ],
        execution_context=ExecutionContext(
            request_id="req_rag_001",
            session_id="sess_rag_001",
            plan_id=None,
            trace_id="trace_rag_001",
            source="react",
        ),
    )

    reloaded = FileBackedSTM(storage_path=storage_path)

    assert result.observation is not None
    assert result.observation["source"] == "rag"
    rag_result = result.observation["result"]
    assert rag_result["chunks"][0]["document_id"] == "protocol"
    history = reloaded.latest_context_snapshot().perception["conversation_messages"]
    assert history[0] == {"role": "user", "content": "搜索协议"}
    assert '"document_id": "protocol"' in history[1]["content"]


def test_pipeline_skill_round_links_directory_loading_and_stm(tmp_path: Path) -> None:
    storage_path = tmp_path / ".mz_agent" / "skill_stm.json"
    skill_root = tmp_path / "skills"
    writer_dir = skill_root / "writer"
    (writer_dir / "scripts").mkdir(parents=True)
    (writer_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: writer",
                "description: 写作技能",
                "---",
                "",
                "请先整理提纲，再开始写作。",
            ]
        ),
        encoding="utf-8",
    )
    (writer_dir / "scripts" / "outline.py").write_text("print('ok')\n", encoding="utf-8")
    pipeline = Pipeline(
        adapters=AdapterHub(skill=SkillAdapter(skill_roots=[skill_root])),
        stm=FileBackedSTM(storage_path=storage_path),
    )
    snapshot = _prepare_snapshot_for_round(
        snapshot=ContextSnapshot(
            current_plan=None,
            skill_context={"selected_skill": "writer"},
        ),
        goal="使用写作技能",
        action_type="skill",
        target="writer",
        draft_answer="任务已收束",
    )

    result = pipeline.run_round(
        goal="使用写作技能",
        context_snapshot=snapshot,
        available_actions=[
            AvailableAction(
                action_type="skill",
                targets=["writer"],
                availability="available",
            )
        ],
        execution_context=ExecutionContext(
            request_id="req_skill_001",
            session_id="sess_skill_001",
            plan_id=None,
            trace_id="trace_skill_001",
            source="react",
        ),
    )

    reloaded = FileBackedSTM(storage_path=storage_path)

    assert result.observation is not None
    assert result.observation["source"] == "skill"
    skill_result = result.observation["result"]
    assert skill_result["selected_skill"] == "writer"
    assert skill_result["resource_manifest"] == {"scripts": ["scripts/outline.py"]}
    history = reloaded.latest_context_snapshot().perception["conversation_messages"]
    assert history[0] == {"role": "user", "content": "使用写作技能"}
    assert '"selected_skill": "writer"' in history[1]["content"]


def test_pipeline_clarify_round_persists_answer_chain_output(tmp_path: Path) -> None:
    storage_path = tmp_path / ".mz_agent" / "clarify_stm.json"
    pipeline = Pipeline(stm=FileBackedSTM(storage_path=storage_path))
    snapshot = _prepare_snapshot_for_round(
        snapshot=ContextSnapshot(current_plan=None),
        goal="帮我处理一下",
        action_type="tool",
        target=None,
        draft_answer="任务已收束",
    )

    result = pipeline.run_round(
        goal="帮我处理一下",
        context_snapshot=snapshot,
        available_actions=[
            AvailableAction(
                action_type="clarify",
                targets=[],
                availability="available",
            )
        ],
        execution_context=ExecutionContext(
            request_id="req_clarify_001",
            session_id="sess_clarify_001",
            plan_id=None,
            trace_id="trace_clarify_001",
            source="react",
        ),
    )

    reloaded = FileBackedSTM(storage_path=storage_path)

    assert snapshot.perception["clarify_needed"] is True
    assert result.output_text == "请补充必要信息。"
    history = reloaded.latest_context_snapshot().perception["conversation_messages"]
    assert history[0] == {"role": "user", "content": "帮我处理一下"}
    assert history[1] == {"role": "assistant", "content": "请补充必要信息。"}
