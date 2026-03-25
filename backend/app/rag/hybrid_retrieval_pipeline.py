"""
混合检索算法 - 核心实现（第一部分）

包含：
1. 查询扩展
2. 并行检索
3. RRF融合
"""

import asyncio
from typing import List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class FusedResult:
    """RRF融合结果"""
    doc_id: str
    content: str
    rrf_score: float
    rrf_rank: int
    top_rank_bonus: float
    source_type: str
    source_bonus: float
    fused_score: float
    metadata: Dict = None


@dataclass
class RerankResult:
    """Rerank最终结果"""
    doc_id: str
    content: str
    rrf_score: float
    rrf_rank: int
    rerank_score: float
    rerank_confidence: float
    final_score: float
    blend_ratio: Tuple[float, float]
    source_type: str
    source_bonus: float
    metadata: Dict = None


class HybridRetrievalPipeline:
    """
    混合检索完整流程
    
    算法流程：
    1. 查询扩展：原问题×2 + LLM生成n个扩展问题
    2. 并行检索：BM25 + 向量检索
    3. RRF融合：k=60，添加Top-Rank Bonus
    4. Rerank重排序：qwen3-reranker
    5. 位置感知混合：根据RRF排名动态调整权重
    6. 上下文整合：Top-5结果
    """
    
    def __init__(self, llm_client, bm25_index, vector_index, reranker_client, n_expansions: int = 2):
        self.llm_client = llm_client
        self.bm25_index = bm25_index
        self.vector_index = vector_index
        self.reranker_client = reranker_client
        self.n_expansions = n_expansions
        self.rrf_k = 60
        self.top_k_for_rerank = 30
        self.final_top_k = 5
        self.retrieval_top_k = 50
        self.product_detail_keywords = (
            '价格', '多少钱', '规格', '参数', '功率', '容量', '尺寸', '材质',
            '型号', '技术', '性能', '适合', '区别', '对比', '卖点', '细节',
            '配置', '功能', '特点',
        )
        self.faq_keywords = (
            '发货', '物流', '售后', '保修', '退货', '退款', '换货', '赠品',
            '下单', '支付', '发票', '包邮', '多久', '质保', '客服', '规则',
            '注意事项', '怎么清洗', '怎么安装', '使用说明',
        )
    
    async def retrieve(
        self,
        query: str,
        source_hint: str | None = None,
    ) -> Tuple[str, List[RerankResult]]:
        """执行完整检索流程"""
        effective_source_hint = source_hint or self._infer_source_hint(query)
        expanded_queries = await self._expand_query(query)
        all_results = await self._parallel_retrieve(expanded_queries)
        fused_results = await self._rrf_fusion(all_results, effective_source_hint)
        rerank_results = await self._rerank(query, fused_results)
        rerank_results = self._apply_source_preference(rerank_results, effective_source_hint)
        context = self._build_context(rerank_results)
        return context, rerank_results

    def _infer_source_hint(self, query: str) -> str:
        detail_hits = sum(keyword in query for keyword in self.product_detail_keywords)
        faq_hits = sum(keyword in query for keyword in self.faq_keywords)

        if detail_hits and faq_hits:
            return 'mixed'
        if detail_hits:
            return 'product_detail'
        if faq_hits:
            return 'faq'
        return 'mixed'

    def _detect_source_type(self, metadata: Dict | None) -> str:
        source_file = str((metadata or {}).get('source_file', ''))
        if '商品详情' in source_file:
            return 'product_detail'
        if 'FAQ' in source_file or '常见问题' in source_file:
            return 'faq'
        return 'other'

    def _source_bonus(self, source_hint: str, source_type: str) -> float:
        if source_hint == 'mixed' or source_type == 'other':
            return 0.0
        if source_hint == source_type:
            return 0.12
        return -0.04

    def _apply_source_preference(
        self,
        rerank_results: List[RerankResult],
        source_hint: str,
    ) -> List[RerankResult]:
        if source_hint == 'mixed':
            return rerank_results

        preferred = [result for result in rerank_results if result.source_type == source_hint]
        if not preferred:
            return rerank_results

        def sort_key(result: RerankResult):
            if result.source_type == source_hint:
                group = 0
            elif result.source_type == 'other':
                group = 1
            else:
                group = 2
            return (group, -result.final_score, result.rrf_rank)

        return sorted(rerank_results, key=sort_key)
    
    # ============ 步骤1：查询扩展 ============
    
    async def _expand_query(self, query: str) -> Dict[str, List[Tuple[str, float]]]:
        """查询扩展：原问题×2 + n个扩展问题"""
        original_queries = [(query, 1.0), (query, 1.0)]

        system_prompt = "你是查询扩展助手，请为用户问题生成不同表述的扩展问题，每行一个，不要编号。"
        user_prompt = f"原问题：{query}\n\n请生成 {self.n_expansions} 个扩展问题："

        try:
            # 用 ainvoke_json 的 llm_client，但这里需要纯文本，直接调 _client
            if hasattr(self.llm_client, '_client') and self.llm_client._client is not None:
                from langchain_core.messages import SystemMessage, HumanMessage
                resp = await self.llm_client._client.ainvoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ])
                raw = resp.content
            else:
                raw = ''
            expansions = [q.strip() for q in raw.split('\n') if q.strip()][:self.n_expansions]
        except Exception as e:
            expansions = []

        expansion_queries = [(q, 0.7) for q in expansions]
        return {'original': original_queries, 'expansions': expansion_queries}
    
    # ============ 步骤2：并行检索 ============
    
    async def _parallel_retrieve(self, expanded_queries: Dict) -> List[Dict]:
        """并行检索：BM25 + 向量"""
        async def retrieve_single(query: str, weight: float) -> Dict:
            bm25_result, vector_result = await asyncio.gather(
                self._bm25_search(query),
                self._vector_search(query),
                return_exceptions=True,
            )

            return {
                'query': query,
                'weight': weight,
                'bm25': [] if isinstance(bm25_result, Exception) else bm25_result,
                'vector': [] if isinstance(vector_result, Exception) else vector_result,
            }

        query_weights: Dict[str, float] = {}
        for query, weight in expanded_queries['original'] + expanded_queries['expansions']:
            query_weights[query] = query_weights.get(query, 0.0) + weight

        query_plan = list(query_weights.items())
        return await asyncio.gather(
            *(retrieve_single(query, weight) for query, weight in query_plan)
        )
    
    async def _bm25_search(self, query: str) -> List[Dict]:
        """BM25全文搜索"""
        try:
            return await self.bm25_index.search(query, top_k=self.retrieval_top_k)
        except Exception as e:
            print(f"BM25搜索失败: {e}")
            return []
    
    async def _vector_search(self, query: str) -> List[Dict]:
        """向量相似度搜索"""
        try:
            return await self.vector_index.search(query, top_k=self.retrieval_top_k)
        except Exception as e:
            print(f"向量搜索失败: {e}")
            return []
    
    # ============ 步骤3：RRF融合 ============
    
    async def _rrf_fusion(
        self,
        all_retrieval_results: List[Dict],
        source_hint: str,
    ) -> List[FusedResult]:
        """RRF融合：score = Σ(1/(k+rank+1))，k=60"""
        doc_scores = {}
        
        for result_set in all_retrieval_results:
            query_weight = result_set['weight']
            
            # 处理BM25结果
            for rank, doc in enumerate(result_set['bm25'], 1):
                rrf_score = 1.0 / (self.rrf_k + rank + 1)
                weighted_score = rrf_score * query_weight
                
                doc_id = doc.get('doc_id')
                metadata = dict(doc.get('metadata', {}) or {})
                if doc.get('source_file') and 'source_file' not in metadata:
                    metadata['source_file'] = doc.get('source_file')
                if doc_id not in doc_scores:
                    doc_scores[doc_id] = {
                        'content': doc.get('content', ''),
                        'rrf_score': 0,
                        'top_ranks': [],
                        'metadata': metadata,
                    }
                
                doc_scores[doc_id]['rrf_score'] += weighted_score
                doc_scores[doc_id]['top_ranks'].append(rank)
            
            # 处理向量结果
            for rank, doc in enumerate(result_set['vector'], 1):
                rrf_score = 1.0 / (self.rrf_k + rank + 1)
                weighted_score = rrf_score * query_weight
                
                doc_id = doc.get('doc_id')
                metadata = dict(doc.get('metadata', {}) or {})
                if doc.get('source_file') and 'source_file' not in metadata:
                    metadata['source_file'] = doc.get('source_file')
                if doc_id not in doc_scores:
                    doc_scores[doc_id] = {
                        'content': doc.get('content', ''),
                        'rrf_score': 0,
                        'top_ranks': [],
                        'metadata': metadata,
                    }
                
                doc_scores[doc_id]['rrf_score'] += weighted_score
                doc_scores[doc_id]['top_ranks'].append(rank)
        
        # 计算Top-Rank Bonus
        fused_results = []
        for rrf_rank, (doc_id, info) in enumerate(
            sorted(doc_scores.items(), key=lambda x: x[1]['rrf_score'], reverse=True),
            1
        ):
            bonus = 0.0
            if 1 in info['top_ranks']:
                bonus += 0.05
            if any(rank in [2, 3] for rank in info['top_ranks']):
                bonus += 0.02
            source_type = self._detect_source_type(info['metadata'])
            source_bonus = self._source_bonus(source_hint, source_type)
            
            fused_results.append(FusedResult(
                doc_id=doc_id,
                content=info['content'],
                rrf_score=info['rrf_score'],
                rrf_rank=rrf_rank,
                top_rank_bonus=bonus,
                source_type=source_type,
                source_bonus=source_bonus,
                fused_score=info['rrf_score'] + bonus + source_bonus,
                metadata=info['metadata'],
            ))
        
        fused_results.sort(key=lambda item: item.fused_score, reverse=True)
        return fused_results
    
    # ============ 步骤4-6：Rerank + 位置感知混合 ============
    
    async def _rerank(self, query: str, fused_results: List[FusedResult]) -> List[RerankResult]:
        """Rerank重排序 + 位置感知混合"""
        candidates = fused_results[:self.top_k_for_rerank]
        
        rerank_inputs = [{'query': query, 'document': c.content} for c in candidates]
        
        try:
            rerank_scores = await self.reranker_client.rerank(rerank_inputs)
        except Exception as e:
            print(f"Rerank失败: {e}")
            rerank_scores = [{'score': c.fused_score, 'confidence': 0.5} for c in candidates]
        
        rerank_results = []
        for candidate, rerank_score in zip(candidates, rerank_scores):
            # 位置感知混合
            if candidate.rrf_rank <= 3:
                retrieval_weight, rerank_weight = 0.75, 0.25
            elif candidate.rrf_rank <= 10:
                retrieval_weight, rerank_weight = 0.60, 0.40
            else:
                retrieval_weight, rerank_weight = 0.40, 0.60

            final_score = (
                candidate.fused_score * retrieval_weight +
                rerank_score.get('score', 0) * rerank_weight
            )
            
            rerank_results.append(RerankResult(
                doc_id=candidate.doc_id,
                content=candidate.content,
                rrf_score=candidate.rrf_score,
                rrf_rank=candidate.rrf_rank,
                rerank_score=rerank_score.get('score', 0),
                rerank_confidence=rerank_score.get('confidence', 0.0),
                final_score=final_score,
                blend_ratio=(retrieval_weight, rerank_weight),
                source_type=candidate.source_type,
                source_bonus=candidate.source_bonus,
                metadata=candidate.metadata,
            ))
        
        rerank_results.sort(key=lambda x: x.final_score, reverse=True)
        return rerank_results
    
    # ============ 步骤7：上下文整合 ============
    
    def _build_context(self, rerank_results: List[RerankResult]) -> str:
        """上下文整合：Top-5结果"""
        context_parts = []
        
        for rank, result in enumerate(rerank_results[:self.final_top_k], 1):
            context_parts.append(f"""
【参考资料 {rank}】
相关度：{result.final_score:.2%}
RRF排名：{result.rrf_rank}
Rerank分数：{result.rerank_score:.2%}
混合比例：检索{result.blend_ratio[0]:.0%} + Rerank{result.blend_ratio[1]:.0%}
资料类型：{result.source_type}
内容：
{result.content}
---
""")
        
        return "\n".join(context_parts)
