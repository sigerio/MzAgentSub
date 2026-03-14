from mz_agent.adapters.rag import RAGAdapter
from mz_agent.contracts.context import ExecutionContext
from mz_agent.knowledge import KnowledgeBase


def test_knowledge_base_imports_documents_and_returns_ranked_chunks(tmp_path) -> None:
    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    (knowledge_root / "protocol.md").write_text(
        "# 协议冻结总表\n\n协议状态机与字段约束已经冻结。\n\n协议对象禁止额外字段。",
        encoding="utf-8",
    )
    (knowledge_root / "notes.txt").write_text(
        "这是其他主题，不包含目标关键字。",
        encoding="utf-8",
    )

    knowledge_base = KnowledgeBase(chunk_size=20)
    knowledge_base.ingest_directory(root=knowledge_root)
    result = knowledge_base.query(query="协议", top_k=2, score_threshold=0.5)

    assert len(result) == 2
    assert result[0]["document_id"] == "protocol"
    assert result[0]["source_path"] == str((knowledge_root / "protocol.md").resolve())
    assert "协议" in result[0]["text"]
    assert result[0]["score"] >= result[1]["score"]


def test_rag_adapter_reads_from_knowledge_base_without_taking_over_building(tmp_path) -> None:
    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    (knowledge_root / "guardrails.md").write_text(
        "# Guardrails\n\n风险判定映射与协议冻结表需要一起核对。",
        encoding="utf-8",
    )
    knowledge_base = KnowledgeBase()
    knowledge_base.ingest_directory(root=knowledge_root)
    adapter = RAGAdapter(
        knowledge_base=knowledge_base,
        score_threshold=0.5,
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    result = adapter.retrieve(query=" Guardrails ", execution_context=execution_context)

    assert result["query"] == "guardrails"
    assert result["trace_id"] == "trace_001"
    assert result["chunks"] == [
        {
            "chunk_id": "guardrails#0",
            "document_id": "guardrails",
            "source_path": str((knowledge_root / "guardrails.md").resolve()),
            "title": "guardrails",
            "text": "# Guardrails",
            "score": 1.0,
        }
    ]


def test_rag_adapter_can_disable_query_rewrite() -> None:
    adapter = RAGAdapter(
        knowledge_chunks=[{"text": "协议冻结总表", "score": 0.9}],
        enable_rewrite_query=False,
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    result = adapter.retrieve(query=" 协议 ", execution_context=execution_context)

    assert result["query"] == " 协议 "
    assert result["chunks"] == []


def test_rag_adapter_returns_empty_chunks_without_turning_no_hit_into_error(tmp_path) -> None:
    knowledge_root = tmp_path / "knowledge"
    knowledge_root.mkdir()
    (knowledge_root / "other.md").write_text(
        "# 其他主题\n\n这里只讨论缓存目录。",
        encoding="utf-8",
    )
    knowledge_base = KnowledgeBase()
    knowledge_base.ingest_directory(root=knowledge_root)
    adapter = RAGAdapter(
        knowledge_base=knowledge_base,
        score_threshold=0.5,
    )
    execution_context = ExecutionContext(
        request_id="req_001",
        session_id="sess_001",
        plan_id=None,
        trace_id="trace_001",
        source="react",
    )

    result = adapter.retrieve(query="协议", execution_context=execution_context)

    assert result["chunks"] == []
    assert result["query"] == "协议"
