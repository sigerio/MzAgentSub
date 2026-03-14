from mz_agent.adapters.rag import RAGAdapter
from mz_agent.contracts.context import ExecutionContext


def test_rag_adapter_filters_by_threshold_and_top_k() -> None:
    adapter = RAGAdapter(
        knowledge_chunks=[
            {"text": "协议冻结总表", "score": 0.95},
            {"text": "协议状态机", "score": 0.9},
            {"text": "协议草稿", "score": 0.4},
        ],
        top_k=1,
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

    assert result == {
        "query": "协议",
        "score_threshold": 0.5,
        "chunks": [{"text": "协议冻结总表", "score": 0.95}],
        "trace_id": "trace_001",
    }


def test_rag_adapter_returns_empty_chunks_without_turning_no_hit_into_error() -> None:
    adapter = RAGAdapter(
        knowledge_chunks=[{"text": "其他主题", "score": 0.9}],
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
