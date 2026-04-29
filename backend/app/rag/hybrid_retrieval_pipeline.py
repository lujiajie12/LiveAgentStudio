"""
混合检索算法 - 核心实现（第一部分）

包含：
1. 查询扩展
2. 并行检索
3. RRF融合
"""

import asyncio
import json
from typing import List, Dict, Tuple
from dataclasses import dataclass

from app.rag.query_constraints import (
    canonicalize_query_with_budget,
    extract_catalog_attributes,
    extract_query_budget,
    normalize_budget_constraint,
    price_constraint_bonus,
)

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
    
    def __init__(self, llm_client, bm25_index, vector_index, reranker_client, n_expansions: int = 1):
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

    def _get_expand_model(self):
        """轻量扩展模型：纯规则，不依赖任何外部模型下载"""
        return None  # 始终返回 None，走规则扩展，完全避免任何网络请求
    
    async def retrieve(
        self,
        query: str,
        source_hint: str | None = None,
    ) -> Tuple[str, List[RerankResult]]:
        """执行完整检索流程（已优化：规则解析 + 轻量扩展 + 扩展与检索并行）"""
        from time import perf_counter
        import logging
        logger = logging.getLogger(__name__)
        t0 = perf_counter()

        # 规则化预算解析，无需 LLM 调用
        budget_constraint = extract_query_budget(query)
        normalized_query = canonicalize_query_with_budget(query, budget_constraint)
        t1 = perf_counter()
        logger.info(f"[RETRIEVE] rule_parse t={((t1-t0)*1000):.0f}ms query='{query[:30]}' normalized='{normalized_query[:30]}'")

        effective_source_hint = source_hint or self._infer_source_hint(normalized_query)
        # 扩展和检索真正并行执行：primary_retrieve 和 _expand_query 同时发起
        original_only = {'original': [(query, 1.0)], 'expansions': []}
        primary_task = self._parallel_retrieve(original_only, budget_hint=budget_constraint)
        expand_task = self._expand_query(normalized_query)
        primary_results, expanded_queries = await asyncio.gather(primary_task, expand_task)
        t2 = perf_counter()
        logger.info(f"[RETRIEVE] primary+expand t={((t2-t1)*1000):.0f}ms primary_docs={len(primary_results)} expansions={len(expanded_queries.get('expansions',[]))}")
        all_results = primary_results
        if expanded_queries['expansions']:
            extra_results = await self._parallel_retrieve(expanded_queries, budget_hint=budget_constraint)
            t3 = perf_counter()
            logger.info(f"[RETRIEVE] extra_retrieve t={((t3-t2)*1000):.0f}ms docs={len(extra_results)}")
            all_results = all_results + extra_results
        fused_results = await self._rrf_fusion(
            normalized_query,
            all_results,
            effective_source_hint,
            budget_hint=budget_constraint,
        )
        t4 = perf_counter()
        logger.info(f"[RETRIEVE] fusion t={((t4-t3 if expanded_queries['expansions'] else t4-t2)*1000):.0f}ms candidates={len(fused_results)}")
        rerank_results = await self._rerank(normalized_query, fused_results)
        t5 = perf_counter()
        logger.info(f"[RETRIEVE] rerank t={((t5-t4)*1000):.0f}ms results={len(rerank_results)}")
        rerank_results = self._apply_source_preference(rerank_results, effective_source_hint)
        context = self._build_context(rerank_results)
        t6 = perf_counter()
        logger.info(f"[RETRIEVE] total t={((t6-t0)*1000):.0f}ms")
        return context, rerank_results

    async def normalize_query_semantics(self, query: str) -> dict:
        # 这层专门负责把口语化预算语义规范化成统一 query 和预算对象。
        # 主路径交给轻量模型理解“80块钱左右 / 100来块 / 300出头”这类表达，
        # 规则只作为模型不可用时的兜底，而不是主要决策器。
        fallback_budget = extract_query_budget(query)
        fallback_query = canonicalize_query_with_budget(query, fallback_budget)
        fallback_payload = {
            "normalized_query": fallback_query,
            "budget_constraint": fallback_budget,
            "reason": "rule_fallback",
        }

        if self.llm_client is None:
            return fallback_payload

        system_prompt = (
            "You normalize live-commerce retrieval queries.\n"
            "Preserve the product intent, but standardize colloquial Chinese budget phrasing into a canonical form.\n"
            "Examples:\n"
            "- 夏凉被80块钱左右的推荐有无 -> 夏凉被80元左右的推荐有无\n"
            "- 100来块的吹风机 -> 100元左右的吹风机\n"
            "- 300出头的空气炸锅 -> 300元左右的空气炸锅\n"
            "- 500以内的扫地机 -> 500元以内的扫地机\n"
            "- 300到500的宠物烘干箱 -> 300-500元的宠物烘干箱\n"
            "Return strict JSON only with keys normalized_query, budget_constraint, reason.\n"
            "budget_constraint must be null or an object with mode, display, target, min_price, max_price.\n"
            "Valid modes: around, range, ceiling, floor."
        )
        user_prompt = json.dumps(
            {
                "query": query,
                "fallback_budget_constraint": fallback_budget,
            },
            ensure_ascii=False,
        )
        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
        except Exception:
            return fallback_payload

        normalized_budget = normalize_budget_constraint(payload.get("budget_constraint"))
        normalized_query = canonicalize_query_with_budget(
            str(payload.get("normalized_query") or fallback_query).strip() or fallback_query,
            normalized_budget or fallback_budget,
        )
        return {
            "normalized_query": normalized_query,
            "budget_constraint": normalized_budget or fallback_budget,
            "reason": str(payload.get("reason") or "llm_budget_normalization").strip() or "llm_budget_normalization",
        }

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

    def _normalize_lookup_text(self, value: str) -> str:
        return str(value or '').strip().lower()

    def _structured_match_bonus(
        self,
        query: str,
        metadata: Dict | None,
        content: str,
        budget_hint: dict | None = None,
    ) -> float:
        enriched_metadata = dict(metadata or {})
        enriched_metadata.update(extract_catalog_attributes(content, enriched_metadata))
        normalized_query = self._normalize_lookup_text(query)
        normalized_title = self._normalize_lookup_text(enriched_metadata.get('product_name'))
        normalized_sku = self._normalize_lookup_text(enriched_metadata.get('sku'))
        normalized_section_title = self._normalize_lookup_text(enriched_metadata.get('section_title'))

        bonus = 0.0
        # 企业化检索里，结构化字段的 exact / near-exact 命中应当显式加权，
        # 否则“朴川空气炸锅介绍下”会被一堆“别的空气炸锅”稀释掉。
        if normalized_title:
            if normalized_title in normalized_query:
                bonus += 0.18
            elif normalized_query in normalized_title:
                bonus += 0.12
        if normalized_sku and normalized_sku in normalized_query:
            bonus += 0.22
        if normalized_section_title and normalized_title and normalized_title in normalized_section_title:
            bonus += 0.04
        if normalized_title and normalized_title in self._normalize_lookup_text(content[:160]):
            bonus += 0.05
        # 预算匹配属于强约束信号，用户说“400 元左右”时，399 元应该稳定压过 79 元。
        bonus += price_constraint_bonus(query, enriched_metadata, content, budget_hint=budget_hint)
        return bonus

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

    async def _expand_query_with_llm(self, query: str) -> list[str]:
        """使用百炼 qwen-turbo 做查询扩展（run_in_executor + wait_for 实现真正 timeout）"""
        import asyncio
        import logging
        logger = logging.getLogger(__name__)

        def _call():
            import dashscope
            from dashscope import Generation
            from app.core.config import settings
            dashscope.api_key = settings.DASHSCOPE_API_KEY or settings.LLM_API_KEY
            prompt = (
                f"请为以下直播电商用户问题生成1个不同表述的扩展问题，"
                f"直接输出扩展问题本身，不要解释，每行一个：\n用户问题：{query}"
            )
            resp = Generation.call(
                "qwen-turbo",
                message=[{"role": "user", "content": prompt}],
                result_format="message",
                timeout=10,
            )
            if resp.status_code == 200:
                content = resp.output.choices[0].message.content or ""
                for line in content.split("\n"):
                    line = line.strip()
                    if line:
                        return [line]
            return []

        loop = asyncio.get_event_loop()
        try:
            expansions = await asyncio.wait_for(
                loop.run_in_executor(None, _call),
                timeout=8
            )
        except asyncio.TimeoutError:
            logger.info("[RETRIEVE] qwen-turbo expand timeout")
            expansions = []
        except Exception:
            expansions = []

        if not expansions:
            expansions = self._expand_query_rule_fallback(query)
        return expansions[:1]

    def _expand_query_rule_fallback(self, query: str) -> list[str]:
        """规则扩展：提取品类词/产品词生成扩展表述（兜底）"""
        import re
        words = re.findall(r'[\u4e00-\u9fff]+', query)
        product_word = max(words, key=len) if words else query
        expansions = []
        if any(kw in query for kw in ['推荐', '有无', '有没有', '款']):
            expansions.append(f"{product_word}怎么样")
        if any(kw in query for kw in ['价格', '多少钱', '多少']):
            expansions.append(f"{product_word}多少钱")
        if any(kw in query for kw in ['适合', '怎么样']):
            expansions.append(f"{product_word}好不好")
        return expansions[:1]

    async def _expand_query(self, query: str) -> Dict[str, List[Tuple[str, float]]]:
        """查询扩展：原问题×2 + 百炼 qwen-turbo 生成1个扩展"""
        original_queries = [(query, 1.0), (query, 1.0)]
        expansions = await self._expand_query_with_llm(query)
        expansion_queries = [(q, 0.7) for q in expansions[:self.n_expansions]]
        return {'original': original_queries, 'expansions': expansion_queries}

    async def _expand_query_fast(self, query: str) -> Dict[str, List[Tuple[str, float]]]:
        """快速查询扩展：规则+轻量模型混合，无任何 LLM 远程调用"""
        original_queries = [(query, 1.0), (query, 1.0)]
        expansions = self._expand_query_rule_fallback(query)
        expansion_queries = [(q, 0.7) for q in expansions[:self.n_expansions]]
        return {'original': original_queries, 'expansions': expansion_queries}

    # ============ 步骤2：并行检索 ============
    
    async def _parallel_retrieve(self, expanded_queries: Dict, budget_hint: dict | None = None) -> List[Dict]:
        """并行检索：BM25 + 向量"""
        async def retrieve_single(query: str, weight: float) -> Dict:
            bm25_result, vector_result = await asyncio.gather(
                self._bm25_search(query, budget_hint=budget_hint),
                self._vector_search(query, budget_hint=budget_hint),
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
    
    async def _bm25_search(self, query: str, budget_hint: dict | None = None) -> List[Dict]:
        """BM25全文搜索"""
        try:
            return await self.bm25_index.search(query, top_k=self.retrieval_top_k, budget_hint=budget_hint)
        except Exception:
            return []
    
    async def _vector_search(self, query: str, budget_hint: dict | None = None) -> List[Dict]:
        """向量相似度搜索"""
        try:
            return await self.vector_index.search(query, top_k=self.retrieval_top_k, budget_hint=budget_hint)
        except Exception:
            return []
    
    # ============ 步骤3：RRF融合 ============
    
    async def _rrf_fusion(
        self,
        query: str,
        all_retrieval_results: List[Dict],
        source_hint: str,
        budget_hint: dict | None = None,
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
            structured_bonus = self._structured_match_bonus(
                query,
                info['metadata'],
                info['content'],
                budget_hint=budget_hint,
            )
            
            fused_results.append(FusedResult(
                doc_id=doc_id,
                content=info['content'],
                rrf_score=info['rrf_score'],
                rrf_rank=rrf_rank,
                top_rank_bonus=bonus + structured_bonus,
                source_type=source_type,
                source_bonus=source_bonus,
                fused_score=info['rrf_score'] + bonus + structured_bonus + source_bonus,
                metadata=info['metadata'],
            ))
        
        fused_results.sort(key=lambda item: item.fused_score, reverse=True)
        return fused_results
    
    # ============ 步骤4-6：Rerank + 位置感知混合 ============
    
    async def _rerank(self, query: str, fused_results: List[FusedResult]) -> List[RerankResult]:
        """Rerank重排序 + 位置感知混合"""
        from time import perf_counter
        import logging
        logger = logging.getLogger(__name__)
        t0 = perf_counter()

        candidates = fused_results[:self.top_k_for_rerank]

        rerank_inputs = [{'query': query, 'document': c.content} for c in candidates]

        try:
            rerank_scores = await self.reranker_client.rerank(rerank_inputs)
        except Exception:
            rerank_scores = [{'score': c.fused_score, 'confidence': 0.5} for c in candidates]

        t1 = perf_counter()
        logger.info(f"[RETRIEVE] rerank_call t={((t1-t0)*1000):.0f}ms reranker={type(self.reranker_client).__name__} candidates={len(candidates)}")
        
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
        """上下文整合：Top-5结果（精简版，去掉技术元数据）"""
        context_parts = []

        for rank, result in enumerate(rerank_results[:self.final_top_k], 1):
            source_label = {'product_detail': '【商品详情】', 'faq': '【常见问题】', 'other': ''}.get(result.source_type, '')
            context_parts.append(f"""{source_label}参考资料 {rank}：
{result.content}
""")

        return "\n".join(context_parts)
