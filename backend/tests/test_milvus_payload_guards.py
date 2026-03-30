import json

import pytest

from app.rag.document_pipeline import sanitize_metadata
from app.rag.embedding import MilvusVectorStore
from app.schemas.document import DocumentChunk


def test_sanitize_metadata_drops_heavy_loader_fields():
    metadata = {
        "source_file": "faq.xlsx",
        "page_number": 1,
        "text_as_html": "<table>" + ("x" * 10000) + "</table>",
        "section_title": "FAQ",
    }

    cleaned = sanitize_metadata(metadata)

    assert cleaned["source_file"] == "faq.xlsx"
    assert cleaned["page_number"] == 1
    assert cleaned["section_title"] == "FAQ"
    assert "text_as_html" not in cleaned
    assert len(json.dumps(cleaned, ensure_ascii=False).encode("utf-8")) <= 8 * 1024


class FailingInsertCollection:
    def __init__(self):
        self.batch_sizes = []
        self.payloads = []
        self.flush_count = 0

    def insert(self, data):
        batch_size = len(data[0])
        self.batch_sizes.append(batch_size)
        self.payloads.append(data)
        if batch_size > 1:
            raise Exception(
                "RESOURCE_EXHAUSTED: grpc: received message larger than max (101134791 vs. 67108864)"
            )

    def flush(self):
        self.flush_count += 1


class SearchCollection:
    def __init__(self):
        self.load_calls = 0

    def load(self):
        self.load_calls += 1

    def search(self, **kwargs):
        _ = kwargs
        return []


@pytest.mark.asyncio
async def test_insert_chunks_splits_and_sanitizes_on_payload_limit():
    store = MilvusVectorStore()
    store.collection = FailingInsertCollection()

    chunks = [
        DocumentChunk(
            chunk_id=f"chunk-{index}",
            document_id="faq.xlsx",
            chunk_index=index,
            content="short content",
            token_count=2,
            metadata={
                "source_file": "faq.xlsx",
                "text_as_html": "x" * 500000,
                "page_number": index,
            },
        )
        for index in range(3)
    ]
    embeddings = [[0.1, 0.2, 0.3, 0.4] for _ in chunks]

    await store.insert_chunks(chunks, embeddings)

    assert store.collection.flush_count == 1
    assert store.collection.batch_sizes[0] == 3
    assert store.collection.batch_sizes.count(1) >= 3

    final_payloads = [payload for payload in store.collection.payloads if len(payload[0]) == 1]
    assert final_payloads
    assert "text_as_html" not in final_payloads[0][4][0]


@pytest.mark.asyncio
async def test_search_loads_collection_before_query():
    store = MilvusVectorStore()
    store.collection = SearchCollection()

    result = await store.search(query_embedding=[0.1, 0.2], top_k=1)

    assert result == []
    assert store.collection.load_calls == 1
