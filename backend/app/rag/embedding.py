"""
Embedding model and Milvus vector store utilities.
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.schemas.document import DocumentChunk

logger = logging.getLogger(__name__)

MAX_INSERT_PAYLOAD_BYTES = 48 * 1024 * 1024
MAX_METADATA_VALUE_BYTES = 4 * 1024
MAX_METADATA_TOTAL_BYTES = 8 * 1024
MAX_CONTENT_BYTES = 60 * 1024
HEAVY_METADATA_KEYS = {
    "text_as_html",
    "image_base64",
    "orig_elements",
    "coordinates",
}


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


class EmbeddingModel(ABC):
    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        pass

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        pass

    @abstractmethod
    def get_embedding_dim(self) -> int:
        pass


class BGEEmbeddingModel(EmbeddingModel):
    """
    Local BGE embedding model. Model path and dimension come from settings
    unless overridden explicitly.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        from app.core.config import settings

        self.model_name = model_name or settings.EMBEDDING_MODEL
        self.device = self._resolve_device(device or settings.EMBEDDING_DEVICE)
        self.model = None
        self.embedding_dim = settings.EMBEDDING_DIM
        self.batch_size = max(1, batch_size or settings.EMBEDDING_BATCH_SIZE)

        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(self.model_name, device=self.device)
            logger.info(
                "Loaded embedding model %s on device=%s batch_size=%d",
                self.model_name,
                self.device,
                self.batch_size,
            )
        except ImportError as exc:
            raise ImportError(
                "Please install sentence-transformers: pip install sentence-transformers"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to load embedding model: {exc}") from exc

    async def embed_text(self, text: str) -> List[float]:
        embedding = self.model.encode(text, convert_to_numpy=True, show_progress_bar=False)
        return embedding.tolist()

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self._encode_texts(texts, self.batch_size)

    def get_embedding_dim(self) -> int:
        return self.embedding_dim

    def _resolve_device(self, requested_device: str) -> str:
        if not requested_device:
            return "cpu"
        if not requested_device.startswith("cuda"):
            return requested_device

        try:
            import torch

            if torch.cuda.is_available():
                return requested_device
            logger.warning("CUDA requested but unavailable, falling back to CPU")
        except Exception as exc:
            logger.warning("Unable to probe CUDA availability: %s; falling back to CPU", exc)

        return "cpu"

    def _encode_texts(self, texts: List[str], batch_size: int) -> List[List[float]]:
        try:
            embeddings = self.model.encode(
                texts,
                batch_size=max(1, min(batch_size, len(texts))),
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return embeddings.tolist()
        except RuntimeError as exc:
            message = str(exc)
            is_cuda_oom = self.device.startswith("cuda") and "CUDA out of memory" in message
            if is_cuda_oom and len(texts) > 1:
                logger.warning(
                    "CUDA OOM at batch_size=%d for %d texts, retrying with smaller batches",
                    batch_size,
                    len(texts),
                )
                try:
                    import torch

                    torch.cuda.empty_cache()
                except Exception:
                    pass

                mid = len(texts) // 2
                left = self._encode_texts(texts[:mid], max(1, batch_size // 2))
                right = self._encode_texts(texts[mid:], max(1, batch_size // 2))
                return left + right
            raise


class MilvusVectorStore:
    """
    Milvus vector store wrapper with payload-aware inserts.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        collection_name: str = "knowledge_base",
        embedding_dim: int = None,
    ):
        from app.core.config import settings

        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim or settings.EMBEDDING_DIM
        self.client = None
        self.collection = None
        self._loaded = False

        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections

            self.connections = connections
            self.Collection = Collection
            self.FieldSchema = FieldSchema
            self.CollectionSchema = CollectionSchema
            self.DataType = DataType
        except ImportError as exc:
            raise ImportError("Please install pymilvus: pip install pymilvus") from exc

    async def connect(self):
        try:
            self.connections.connect(alias="default", host=self.host, port=self.port)
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to Milvus: {exc}") from exc

    async def create_collection(self):
        try:
            from pymilvus import utility

            if utility.has_collection(self.collection_name):
                self.collection = self.Collection(self.collection_name)
                self._loaded = False
                return

            fields = [
                self.FieldSchema(name="id", dtype=self.DataType.INT64, is_primary=True, auto_id=True),
                self.FieldSchema(name="chunk_id", dtype=self.DataType.VARCHAR, max_length=256),
                self.FieldSchema(name="document_id", dtype=self.DataType.VARCHAR, max_length=256),
                self.FieldSchema(name="content", dtype=self.DataType.VARCHAR, max_length=65535),
                self.FieldSchema(
                    name="embedding", dtype=self.DataType.FLOAT_VECTOR, dim=self.embedding_dim
                ),
                self.FieldSchema(name="metadata", dtype=self.DataType.JSON),
            ]
            schema = self.CollectionSchema(fields=fields, description="Knowledge base vectors")
            self.collection = self.Collection(name=self.collection_name, schema=schema)
            self._loaded = False
            await self.create_index()
        except Exception as exc:
            raise RuntimeError(f"Failed to create collection: {exc}") from exc

    def _reconnect_collection(self):
        try:
            self.connections.disconnect(alias="default")
        except Exception:
            pass
        self.connections.connect(alias="default", host=self.host, port=self.port)
        self.collection = self.Collection(self.collection_name)
        self._loaded = False

    def _is_retryable_flush_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            token in message
            for token in (
                "channel not found",
                "service unavailable",
                "timed out",
                "collection not loaded",
                "connection refused",
            )
        )

    def _safe_num_entities(self) -> int | None:
        if not self.collection:
            return None
        try:
            return int(self.collection.num_entities)
        except Exception as exc:
            logger.warning("Failed to read Milvus entity count: %s", exc)
            try:
                self._reconnect_collection()
                return int(self.collection.num_entities)
            except Exception as reconnect_exc:
                logger.warning(
                    "Failed to recover Milvus entity count after reconnect: %s",
                    reconnect_exc,
                )
                return None

    def _wait_for_entity_count(
        self,
        minimum_count: int,
        max_attempts: int = 8,
        delay_seconds: float = 2.0,
    ) -> bool:
        for attempt in range(1, max_attempts + 1):
            current = self._safe_num_entities()
            if current is not None and current >= minimum_count:
                return True
            logger.warning(
                "Waiting for Milvus entity count to reach %d (attempt %d/%d, current=%s)",
                minimum_count,
                attempt,
                max_attempts,
                current,
            )
            time.sleep(delay_seconds)
        return False

    async def create_index(self):
        try:
            if not self.collection:
                return
            self.collection.create_index(
                field_name="embedding",
                index_params={"metric_type": "L2", "index_type": "IVF_FLAT", "params": {"nlist": 128}},
            )
        except Exception:
            pass

    def _sanitize_meta(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        if not metadata:
            return {}

        cleaned: Dict[str, Any] = {}
        total_bytes = 2

        for key, value in metadata.items():
            if value is None or key in HEAVY_METADATA_KEYS:
                continue

            if isinstance(value, (str, int, float, bool)):
                normalized: Any = value
            else:
                normalized = json.dumps(value, ensure_ascii=False, default=str)

            key_str = str(key)
            key_bytes = len(key_str.encode("utf-8"))

            if isinstance(normalized, str):
                normalized = _truncate_utf8(normalized, MAX_METADATA_VALUE_BYTES)
                value_bytes = len(normalized.encode("utf-8"))
            else:
                value_bytes = len(str(normalized).encode("utf-8"))

            if total_bytes + key_bytes + value_bytes > MAX_METADATA_TOTAL_BYTES:
                continue

            cleaned[key_str] = normalized
            total_bytes += key_bytes + value_bytes

        return cleaned

    def _normalize_content(self, content: str) -> str:
        return _truncate_utf8(content or "", MAX_CONTENT_BYTES)

    def _estimate_row_bytes(self, chunk: DocumentChunk, embedding: List[float]) -> int:
        metadata = self._sanitize_meta(chunk.metadata)
        metadata_bytes = len(json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
        content_bytes = len(self._normalize_content(chunk.content).encode("utf-8"))
        return (
            len((chunk.chunk_id or "").encode("utf-8"))
            + len((chunk.document_id or "").encode("utf-8"))
            + content_bytes
            + metadata_bytes
            + len(embedding) * 4
            + 1024
        )

    def _build_insert_payload(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]],
    ) -> List[List[Any]]:
        return [
            [chunk.chunk_id for chunk in chunks],
            [chunk.document_id for chunk in chunks],
            [self._normalize_content(chunk.content) for chunk in chunks],
            embeddings,
            [self._sanitize_meta(chunk.metadata) for chunk in chunks],
        ]

    def _iter_insert_batches(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]],
    ):
        batch_chunks: List[DocumentChunk] = []
        batch_embeddings: List[List[float]] = []
        batch_bytes = 0

        for chunk, embedding in zip(chunks, embeddings):
            row_bytes = self._estimate_row_bytes(chunk, embedding)
            if batch_chunks and batch_bytes + row_bytes > MAX_INSERT_PAYLOAD_BYTES:
                yield batch_chunks, batch_embeddings
                batch_chunks, batch_embeddings, batch_bytes = [], [], 0

            batch_chunks.append(chunk)
            batch_embeddings.append(embedding)
            batch_bytes += row_bytes

        if batch_chunks:
            yield batch_chunks, batch_embeddings

    def _insert_batch_with_retry(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]],
    ):
        try:
            self.collection.insert(self._build_insert_payload(chunks, embeddings))
        except Exception as exc:
            message = str(exc)
            is_payload_limit = (
                "RESOURCE_EXHAUSTED" in message
                or "received message larger than max" in message
            )
            if is_payload_limit and len(chunks) > 1:
                mid = len(chunks) // 2
                self._insert_batch_with_retry(chunks[:mid], embeddings[:mid])
                self._insert_batch_with_retry(chunks[mid:], embeddings[mid:])
                return
            raise

    async def _ensure_loaded(self):
        if self.collection and not self._loaded:
            self.collection.load()
            self._loaded = True

    def _flush_with_retry(
        self,
        expected_min_entities: int | None = None,
        max_attempts: int = 6,
        delay_seconds: float = 2.0,
    ):
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                self.collection.flush()
                return
            except Exception as exc:
                last_error = exc
                retryable = self._is_retryable_flush_error(exc)
                if not retryable or attempt == max_attempts:
                    if retryable and expected_min_entities is not None:
                        logger.warning(
                            "Milvus flush still failing after %d attempts, checking entity count before abort: %s",
                            max_attempts,
                            exc,
                        )
                        if self._wait_for_entity_count(expected_min_entities):
                            logger.warning(
                                "Milvus flush did not return cleanly, but entity count reached %d; continuing",
                                expected_min_entities,
                            )
                            return
                    raise
                logger.warning(
                    "Milvus flush attempt %d/%d failed, retrying: %s",
                    attempt,
                    max_attempts,
                    exc,
                )
                time.sleep(delay_seconds * attempt)
                self._reconnect_collection()

    # 对外暴露统一 flush 入口：索引脚本可先连续 insert，再按窗口或末尾集中 flush。
    async def flush(self, expected_min_entities: int | None = None):
        if not self.collection:
            return
        self._flush_with_retry(expected_min_entities=expected_min_entities)

    # 默认仍兼容“写后立刻 flush”；批量重建索引时可显式传 flush=False，把刷盘时机交给上层控制。
    async def insert_chunks(
        self,
        chunks: List[DocumentChunk],
        embeddings: List[List[float]],
        *,
        flush: bool = True,
        expected_min_entities: int | None = None,
    ):
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings length mismatch")

        try:
            count_before = self._safe_num_entities() or 0
            for chunk_batch, embedding_batch in self._iter_insert_batches(chunks, embeddings):
                self._insert_batch_with_retry(chunk_batch, embedding_batch)
            if flush:
                self._flush_with_retry(
                    expected_min_entities=expected_min_entities or (count_before + len(chunks))
                )
        except Exception as exc:
            raise RuntimeError(f"Failed to insert data: {exc}") from exc

    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        try:
            await self._ensure_loaded()
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param={"metric_type": "L2", "params": {"nprobe": 10}},
                limit=top_k,
                output_fields=["chunk_id", "document_id", "content", "metadata"],
            )
            search_results = []
            for hits in results:
                for hit in hits:
                    similarity = 1 / (1 + hit.distance)
                    if similarity >= score_threshold:
                        search_results.append(
                            {
                                "chunk_id": hit.entity.get("chunk_id"),
                                "document_id": hit.entity.get("document_id"),
                                "content": hit.entity.get("content"),
                                "metadata": hit.entity.get("metadata"),
                                "similarity_score": similarity,
                            }
                        )
            return search_results
        except Exception as exc:
            raise RuntimeError(f"Failed to search: {exc}") from exc

    async def delete_by_document_id(self, document_id: str):
        try:
            self.collection.delete(f'document_id == "{document_id}"')
            self.collection.flush()
        except Exception as exc:
            raise RuntimeError(f"Failed to delete data: {exc}") from exc

    async def close(self):
        try:
            self.connections.disconnect(alias="default")
        except Exception:
            pass
