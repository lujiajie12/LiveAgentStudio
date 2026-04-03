"""
BM25Index (LangChain ElasticsearchStore) + VectorIndex (BGEEmbeddingModel + Milvus)
+ DashScopeReranker (阿里百炼) / MockReranker (fallback)
供 HybridRetrievalPipeline 使用
"""
import asyncio
import logging
from typing import List, Dict, Any
from time import perf_counter

from app.core.observability import record_timed_tool_call

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BM25 Index - LangChain ElasticsearchStore
# ---------------------------------------------------------------------------

class BM25Index:
    INDEX_NAME = 'knowledge_base'

    def __init__(self, host: str = 'localhost', port: int = 9200):
        self.host = host
        self.port = port
        self._es = None

    def _get_es(self):
        if self._es is None:
            from elasticsearch import Elasticsearch
            self._es = Elasticsearch(f'http://{self.host}:{self.port}', request_timeout=30)
        return self._es

    async def search(self, query: str, top_k: int = 50) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        started = perf_counter()
        results = await loop.run_in_executor(None, self._search_sync, query, top_k)
        await record_timed_tool_call(
            "bm25_search",
            started_at=started,
            node_name="retrieval",
            category="retrieval",
            input_payload={"query": query, "top_k": top_k},
            output_summary=f"hits={len(results)}",
            status="ok" if results else "degraded",
        )
        return results

    def _search_sync(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        try:
            es = self._get_es()
            resp = es.search(
                index=self.INDEX_NAME,
                query={
                    'multi_match': {
                        'query': query,
                        'fields': ['text'],
                        'type': 'best_fields',
                    }
                },
                size=top_k,
            )
            results = []
            for hit in resp['hits']['hits']:
                src = hit['_source']
                meta = src.get('metadata', {})
                if isinstance(meta, str):
                    import json
                    try: meta = json.loads(meta)
                    except: meta = {}
                results.append({
                    'doc_id':      src.get('chunk_id', hit['_id']),
                    'content':     src.get('text', ''),
                    'score':       hit['_score'],
                    'source_file': src.get('source_file', ''),
                    'metadata':    meta,
                })
            return results
        except Exception as e:
            logger.error('BM25 search error: %s', e)
            return []

    def count(self) -> int:
        try:
            return self._get_es().count(index=self.INDEX_NAME).get('count', 0)
        except Exception:
            return 0

    async def health(self) -> Dict[str, Any]:
        try:
            es = self._get_es()
            ping_ok = es.ping()
            count = self.count()
            return {
                "status": "ok" if ping_ok else "degraded",
                "count": count,
                "host": self.host,
                "port": self.port,
            }
        except Exception as exc:
            return {
                "status": "degraded",
                "count": 0,
                "host": self.host,
                "port": self.port,
                "reason": str(exc),
            }


# ---------------------------------------------------------------------------
# Vector Index - BGEEmbeddingModel + MilvusVectorStore
# ---------------------------------------------------------------------------

class VectorIndex:
    COLLECTION_NAME = 'knowledge_base'

    def __init__(self, host: str = 'localhost', port: int = 19530):
        self.host = host
        self.port = port
        self._embed_model = None
        self._store = None

    def _get_embed_model(self):
        if self._embed_model is None:
            from app.core.config import settings
            from app.rag.embedding import BGEEmbeddingModel
            self._embed_model = BGEEmbeddingModel(
                model_name=settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
            )
        return self._embed_model

    async def _get_store(self):
        if self._store is None:
            from app.rag.embedding import MilvusVectorStore
            self._store = MilvusVectorStore(host=self.host, port=self.port)
            await self._store.connect()
            await self._store.create_collection()
        return self._store

    async def search(self, query: str, top_k: int = 50) -> List[Dict[str, Any]]:
        started = perf_counter()
        try:
            vec = await self._get_embed_model().embed_text(query)
            store = await self._get_store()
            results = await store.search(query_embedding=vec, top_k=top_k, score_threshold=0.0)
            payload = [
                {
                    'doc_id':      r.get('chunk_id', ''),
                    'content':     r.get('content', ''),
                    'score':       r.get('similarity_score', 0.0),
                    'source_file': r.get('metadata', {}).get('source_file', ''),
                    'metadata':    r.get('metadata', {}),
                }
                for r in results
            ]
            await record_timed_tool_call(
                "vector_search",
                started_at=started,
                node_name="retrieval",
                category="retrieval",
                input_payload={"query": query, "top_k": top_k},
                output_summary=f"hits={len(payload)}",
                status="ok" if payload else "degraded",
            )
            return payload
        except Exception as e:
            logger.error('Vector search error: %s', e)
            await record_timed_tool_call(
                "vector_search",
                started_at=started,
                node_name="retrieval",
                category="retrieval",
                input_payload={"query": query, "top_k": top_k},
                output_summary=str(e),
                status="degraded",
            )
            return []

    def count(self) -> int:
        try:
            from pymilvus import Collection, utility, connections
            connections.connect(host=self.host, port=self.port)
            if not utility.has_collection(self.COLLECTION_NAME):
                return 0
            return Collection(self.COLLECTION_NAME).num_entities
        except Exception:
            return 0

    async def health(self) -> Dict[str, Any]:
        try:
            from pymilvus import Collection, utility, connections

            connections.connect(host=self.host, port=self.port)
            has_collection = utility.has_collection(self.COLLECTION_NAME)
            count = Collection(self.COLLECTION_NAME).num_entities if has_collection else 0
            return {
                "status": "ok",
                "count": count,
                "host": self.host,
                "port": self.port,
            }
        except Exception as exc:
            return {
                "status": "degraded",
                "count": 0,
                "host": self.host,
                "port": self.port,
                "reason": str(exc),
            }


# ---------------------------------------------------------------------------
# Local Reranker - BGE cross-encoder
# ---------------------------------------------------------------------------

class LocalReranker:
    def __init__(self, model: str = "BAAI/bge-reranker-base", device: str = "mps"):
        self.model_name = model
        self.device = device
        self.model = None

    def _ensure_model(self):
        if self.model is None:
            try:
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(self.model_name, device=self.device)
                logger.info("Loaded local reranker model %s on device=%s", self.model_name, self.device)
            except ImportError as exc:
                raise ImportError(
                    "Please install sentence-transformers: pip install sentence-transformers"
                ) from exc
            except Exception as exc:
                raise RuntimeError(f"Failed to load reranker model: {exc}") from exc

    async def rerank(self, inputs: List[Dict]) -> List[Dict]:
        if not inputs:
            return []
        self._ensure_model()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._rerank_sync, inputs)

    def _rerank_sync(self, inputs: List[Dict]) -> List[Dict]:
        try:
            query = inputs[0]['query']
            documents = [item['document'] for item in inputs]
            pairs = [[query, doc] for doc in documents]
            scores = self.model.predict(pairs)
            if isinstance(scores[0], (list, tuple)):
                scores = [s[0] for s in scores]
            return [{'score': float(s), 'confidence': float(s)} for s in scores]
        except Exception as e:
            logger.error('Local rerank error: %s', e)
            return [{'score': 0.5, 'confidence': 0.5} for _ in inputs]


# ---------------------------------------------------------------------------
# DashScope Reranker - 阿里百炼 gte-rerank
# ---------------------------------------------------------------------------

class DashScopeReranker:
    def __init__(self, model: str = 'gte-rerank', api_key: str = None):
        self.model = model
        self.api_key = api_key

    async def rerank(self, inputs: List[Dict]) -> List[Dict]:
        if not inputs:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._rerank_sync, inputs)

    def _rerank_sync(self, inputs: List[Dict]) -> List[Dict]:
        try:
            import dashscope
            from dashscope import TextReRank
            if self.api_key:
                dashscope.api_key = self.api_key
            query = inputs[0]['query']
            documents = [item['document'] for item in inputs]
            resp = TextReRank.call(
                model=self.model,
                query=query,
                documents=documents,
                top_n=len(documents),
                return_documents=False,
            )
            if resp.status_code != 200:
                raise Exception(f'DashScope error: {resp.message}')
            # 按原始顺序返回分数
            scores_by_idx = {r.index: r.relevance_score for r in resp.output.results}
            return [
                {'score': scores_by_idx.get(i, 0.0), 'confidence': scores_by_idx.get(i, 0.0)}
                for i in range(len(inputs))
            ]
        except Exception as e:
            logger.error('DashScope rerank error: %s', e)
            return [{'score': 0.5, 'confidence': 0.5} for _ in inputs]


# ---------------------------------------------------------------------------
# Mock Reranker - fallback
# ---------------------------------------------------------------------------

class MockReranker:
    async def rerank(self, inputs: List[Dict]) -> List[Dict]:
        return [{'score': 0.5, 'confidence': 0.5} for _ in inputs]
