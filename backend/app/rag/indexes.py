"""
BM25Index (LangChain ElasticsearchStore) + VectorIndex (BGEEmbeddingModel + Milvus)
+ DashScopeReranker (阿里百炼) / MockReranker (fallback)
供 HybridRetrievalPipeline 使用
"""
import asyncio
import logging
from typing import List, Dict, Any

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
        return await loop.run_in_executor(None, self._search_sync, query, top_k)

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
        try:
            vec = await self._get_embed_model().embed_text(query)
            store = await self._get_store()
            results = await store.search(query_embedding=vec, top_k=top_k, score_threshold=0.0)
            return [
                {
                    'doc_id':      r.get('chunk_id', ''),
                    'content':     r.get('content', ''),
                    'score':       r.get('similarity_score', 0.0),
                    'source_file': r.get('metadata', {}).get('source_file', ''),
                    'metadata':    r.get('metadata', {}),
                }
                for r in results
            ]
        except Exception as e:
            logger.error('Vector search error: %s', e)
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
