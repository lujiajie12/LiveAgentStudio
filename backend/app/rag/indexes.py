"""
BM25Index (LangChain ElasticsearchStore) + VectorIndex (BGEEmbeddingModel + Milvus)
+ DashScopeReranker (阿里百炼) / MockReranker (fallback)
供 HybridRetrievalPipeline 使用
"""
import asyncio
import logging
import re
from typing import List, Dict, Any
from time import perf_counter

from app.core.observability import record_timed_tool_call
from app.rag.query_constraints import extract_catalog_attributes, price_constraint_bonus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BM25 Index - LangChain ElasticsearchStore
# ---------------------------------------------------------------------------

class BM25Index:
    INDEX_NAME = 'knowledge_base'
    SKU_PATTERN = re.compile(r"([A-Za-z0-9\u4e00-\u9fff]+(?:[-_][A-Za-z0-9\u4e00-\u9fff]+)+)")

    def __init__(self, host: str = 'localhost', port: int = 9200):
        self.host = host
        self.port = port
        self._es = None

    def _get_es(self):
        if self._es is None:
            from elasticsearch import Elasticsearch
            self._es = Elasticsearch(f'http://{self.host}:{self.port}', request_timeout=30)
        return self._es

    async def search(
        self,
        query: str,
        top_k: int = 50,
        budget_hint: dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        started = perf_counter()
        results = await loop.run_in_executor(None, self._search_sync, query, top_k, budget_hint)
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

    def _search_sync(
        self,
        query: str,
        top_k: int,
        budget_hint: dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        try:
            es = self._get_es()
            normalized_query = self._normalize_query(query)
            resp = es.search(
                index=self.INDEX_NAME,
                query=self._build_query(normalized_query),
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
                if src.get('section_title') and 'section_title' not in meta:
                    meta['section_title'] = src.get('section_title')
                if src.get('subsection_title') and 'subsection_title' not in meta:
                    meta['subsection_title'] = src.get('subsection_title')
                if src.get('product_name') and 'product_name' not in meta:
                    meta['product_name'] = src.get('product_name')
                if src.get('sku') and 'sku' not in meta:
                    meta['sku'] = src.get('sku')
                if src.get('category') and 'category' not in meta:
                    meta['category'] = src.get('category')
                if src.get('audience') and 'audience' not in meta:
                    meta['audience'] = src.get('audience')
                if src.get('product_type') and 'product_type' not in meta:
                    meta['product_type'] = src.get('product_type')
                if src.get('price_band_text') and 'price_band_text' not in meta:
                    meta['price_band_text'] = src.get('price_band_text')
                if src.get('price_band_low') is not None and 'price_band_low' not in meta:
                    meta['price_band_low'] = src.get('price_band_low')
                if src.get('price_band_high') is not None and 'price_band_high' not in meta:
                    meta['price_band_high'] = src.get('price_band_high')
                meta.update(extract_catalog_attributes(src.get('text', ''), meta))
                results.append({
                    'doc_id':      src.get('chunk_id', hit['_id']),
                    'content':     src.get('text', ''),
                    'score':       float(hit['_score']) + price_constraint_bonus(
                        query,
                        meta,
                        src.get('text', ''),
                        budget_hint=budget_hint,
                    ),
                    'source_file': src.get('source_file', ''),
                    'metadata':    meta,
                })
            return results
        except Exception as e:
            logger.error('BM25 search error: %s', e)
            return []

    def _normalize_query(self, query: str) -> str:
        return " ".join(str(query or "").split()).strip()

    def _extract_sku(self, query: str) -> str:
        match = self.SKU_PATTERN.search(query)
        return match.group(1).strip().lower() if match else ""

    def _build_query(self, query: str) -> Dict[str, Any]:
        # 企业里不会只拿一个 text 字段裸跑 multi_match。
        # 这里把“商品名 / 标题 / 聚合检索字段 / 正文”拆成多字段加权，
        # 让中文商品名自然问句、标题命中和 SKU 命中各自都能发挥作用。
        should: List[Dict[str, Any]] = [
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "product_name^10",
                        "product_type^9",
                        "category^6",
                        "section_title^8",
                        "subsection_title^5",
                        "search_text^4",
                        "text^2",
                        "text.std",
                    ],
                    "type": "most_fields",
                    "operator": "or",
                }
            },
            {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "product_name^16",
                        "product_type^12",
                        "section_title^12",
                        "search_text^8",
                        "text^4",
                    ],
                    "type": "phrase",
                    "boost": 4,
                }
            },
            {
                "match": {
                    "search_text": {
                        "query": query,
                        "operator": "and",
                        "boost": 3,
                    }
                }
            },
        ]

        sku = self._extract_sku(query)
        if sku:
            should.append(
                {
                    "term": {
                        "sku": {
                            "value": sku,
                            "boost": 14,
                        }
                    }
                }
            )

        return {
            "bool": {
                "should": should,
                "minimum_should_match": 1,
            }
        }

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

    async def search(
        self,
        query: str,
        top_k: int = 50,
        budget_hint: dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        started = perf_counter()
        try:
            vec = await self._get_embed_model().embed_text(query)
            store = await self._get_store()
            results = await store.search(query_embedding=vec, top_k=top_k, score_threshold=0.0)
            payload = []
            for r in results:
                metadata = dict(r.get('metadata', {}) or {})
                metadata.update(extract_catalog_attributes(r.get('content', ''), metadata))
                score = float(r.get('similarity_score', 0.0))
                score += self._structured_match_bonus(query, metadata, r.get('content', ''))
                score += price_constraint_bonus(
                    query,
                    metadata,
                    r.get('content', ''),
                    budget_hint=budget_hint,
                )
                payload.append(
                    {
                        'doc_id': r.get('chunk_id', ''),
                        'content': r.get('content', ''),
                        'score': score,
                        'source_file': metadata.get('source_file', ''),
                        'metadata': metadata,
                    }
                )
            payload.sort(key=lambda item: item['score'], reverse=True)
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

    def _normalize_lookup_text(self, value: str) -> str:
        return str(value or "").strip().lower()

    def _structured_match_bonus(self, query: str, metadata: Dict[str, Any], content: str) -> float:
        normalized_query = self._normalize_lookup_text(query)
        normalized_title = self._normalize_lookup_text(metadata.get("product_name"))
        normalized_sku = self._normalize_lookup_text(metadata.get("sku"))

        bonus = 0.0
        # 向量召回负责“语义近似”，但对商品名 / SKU 的精确命中不该视而不见。
        # 这里加一层轻量 bonus，让“朴川空气炸锅”这类 exact match 不会输给泛空气炸锅 FAQ。
        if normalized_title:
            if normalized_title in normalized_query:
                bonus += 0.10
            elif normalized_query in normalized_title:
                bonus += 0.06
        if normalized_sku and normalized_sku in normalized_query:
            bonus += 0.12
        if normalized_title and normalized_title in self._normalize_lookup_text(content[:160]):
            bonus += 0.03
        return bonus

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
