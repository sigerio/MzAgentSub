"""MzAgent 第一阶段最小知识库载体实现。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    source_path: str
    title: str
    content: str


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    source_path: str
    title: str
    text: str


class KnowledgeBase:
    def __init__(self, *, chunk_size: int = 120) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0。")
        self._chunk_size = chunk_size
        self._documents: dict[str, KnowledgeDocument] = {}
        self._chunks: list[KnowledgeChunk] = []

    def ingest_directory(self, *, root: str | Path) -> None:
        root_path = Path(root).expanduser().resolve()
        for file_path in sorted(root_path.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in {".md", ".txt"}:
                continue
            self.ingest_file(path=file_path)

    def ingest_file(self, *, path: str | Path) -> None:
        file_path = Path(path).expanduser().resolve()
        content = file_path.read_text(encoding="utf-8")
        self.ingest_text(
            document_id=file_path.stem,
            title=file_path.stem,
            source_path=str(file_path),
            content=content,
        )

    def ingest_text(
        self,
        *,
        document_id: str,
        title: str,
        source_path: str,
        content: str,
    ) -> None:
        document = KnowledgeDocument(
            document_id=document_id,
            source_path=source_path,
            title=title,
            content=content,
        )
        self._documents[document_id] = document
        self._chunks = [
            chunk for chunk in self._chunks if chunk.document_id != document_id
        ]
        self._chunks.extend(
            _build_chunks(
                document=document,
                chunk_size=self._chunk_size,
            )
        )

    def query(
        self,
        *,
        query: str,
        top_k: int = 3,
        score_threshold: float = 0.5,
    ) -> list[dict[str, object]]:
        normalized_query = query.strip().lower()
        if top_k <= 0:
            return []
        scored_chunks: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self._chunks:
            score = _score_chunk(chunk=chunk, normalized_query=normalized_query)
            if score < score_threshold:
                continue
            scored_chunks.append((score, chunk))
        scored_chunks.sort(
            key=lambda item: (
                -item[0],
                item[1].document_id,
                item[1].chunk_id,
            )
        )
        return [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "source_path": chunk.source_path,
                "title": chunk.title,
                "text": chunk.text,
                "score": round(score, 4),
            }
            for score, chunk in scored_chunks[:top_k]
        ]


def _build_chunks(
    *,
    document: KnowledgeDocument,
    chunk_size: int,
) -> list[KnowledgeChunk]:
    segments = [
        segment.strip()
        for segment in re.split(r"\n\s*\n", document.content)
        if segment.strip()
    ]
    chunks: list[KnowledgeChunk] = []
    if not segments:
        return [
            KnowledgeChunk(
                chunk_id=f"{document.document_id}#0",
                document_id=document.document_id,
                source_path=document.source_path,
                title=document.title,
                text="",
            )
        ]
    for index, segment in enumerate(segments):
        for part_index, part in enumerate(_split_segment(segment=segment, chunk_size=chunk_size)):
            suffix = index if part_index == 0 else f"{index}-{part_index}"
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{document.document_id}#{suffix}",
                    document_id=document.document_id,
                    source_path=document.source_path,
                    title=document.title,
                    text=part,
                )
            )
    return chunks


def _split_segment(*, segment: str, chunk_size: int) -> list[str]:
    if len(segment) <= chunk_size:
        return [segment]
    parts: list[str] = []
    current = segment
    while len(current) > chunk_size:
        split_at = current.rfind(" ", 0, chunk_size + 1)
        if split_at <= 0:
            split_at = chunk_size
        parts.append(current[:split_at].strip())
        current = current[split_at:].strip()
    if current:
        parts.append(current)
    return [part for part in parts if part]


def _score_chunk(*, chunk: KnowledgeChunk, normalized_query: str) -> float:
    if not normalized_query:
        return 1.0
    text = chunk.text.lower()
    query_terms = [term for term in re.split(r"\s+", normalized_query) if term]
    if not query_terms:
        return 1.0
    matched_terms = sum(1 for term in query_terms if term in text)
    if matched_terms == 0:
        return 0.0
    contains_full_query = normalized_query in text
    base_score = matched_terms / len(query_terms)
    return min(1.0, base_score + (0.25 if contains_full_query else 0.0))
