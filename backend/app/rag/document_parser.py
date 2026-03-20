"""Compatibility parser layer for legacy document upload services.

This module adapts the newer document pipeline to the older
``DocumentParserFactory`` interface that other modules still import.
"""

from __future__ import annotations

from pathlib import Path

from app.rag.document_pipeline import load_and_split
from app.schemas.document import DocumentChunk


SUPPORTED_TYPES = {
    "pdf",
    "docx",
    "excel",
    "xlsx",
    "xls",
    "markdown",
    "md",
    "csv",
    "txt",
}


def _normalize_extension(file_type: str) -> str:
    normalized = file_type.lower().lstrip(".")
    if normalized == "excel":
        return "xlsx"
    if normalized == "markdown":
        return "md"
    return normalized


def _estimate_token_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, len(stripped))


class DocumentParser:
    async def parse(self, file_path: str, document_id: str) -> list[DocumentChunk]:
        docs = load_and_split(file_path)
        chunks: list[DocumentChunk] = []

        for index, doc in enumerate(docs):
            metadata = dict(doc.metadata or {})
            chunk_id = metadata.get("chunk_id") or f"{document_id}_{index}"
            chunk_index = int(metadata.get("chunk_index", index))
            chunks.append(
                DocumentChunk(
                    chunk_id=str(chunk_id),
                    document_id=document_id,
                    chunk_index=chunk_index,
                    content=doc.page_content,
                    token_count=_estimate_token_count(doc.page_content),
                    metadata=metadata,
                )
            )

        return chunks


class DocumentParserFactory:
    def get_supported_types(self) -> list[str]:
        return sorted(SUPPORTED_TYPES)

    def get_parser(self, file_type: str) -> DocumentParser:
        normalized = _normalize_extension(file_type)
        if normalized not in SUPPORTED_TYPES:
            raise ValueError(f"Unsupported file type: {file_type}")
        return DocumentParser()

