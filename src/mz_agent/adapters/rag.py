"""MzAgent 第一阶段 RAG 适配壳。"""

from __future__ import annotations

from ..contracts.context import ExecutionContext


class RAGAdapter:
    def __init__(
        self,
        *,
        knowledge_chunks: list[dict[str, object]] | None = None,
        top_k: int = 3,
        score_threshold: float = 0.5,
        enable_rewrite_query: bool = True,
    ) -> None:
        self._knowledge_chunks = knowledge_chunks or []
        self._top_k = top_k
        self._score_threshold = score_threshold
        self._enable_rewrite_query = enable_rewrite_query

    def retrieve(
        self,
        *,
        query: str,
        execution_context: ExecutionContext,
    ) -> dict[str, object]:
        normalized_query = query.strip().lower() if self._enable_rewrite_query else query
        matched_chunks = [
            chunk
            for chunk in self._knowledge_chunks
            if self._matches(
                chunk=chunk,
                query=normalized_query,
                score_threshold=self._score_threshold,
            )
        ][: self._top_k]
        return {
            "query": normalized_query,
            "score_threshold": self._score_threshold,
            "chunks": matched_chunks,
            "trace_id": execution_context.trace_id,
        }

    @staticmethod
    def _matches(
        *,
        chunk: dict[str, object],
        query: str,
        score_threshold: float,
    ) -> bool:
        text = chunk.get("text")
        score = chunk.get("score", 1.0)
        if not isinstance(text, str):
            return False
        if isinstance(score, (int, float)) and float(score) < score_threshold:
            return False
        return query in text.lower() if query else True
