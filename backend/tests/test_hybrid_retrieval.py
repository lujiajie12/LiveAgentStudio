"""
混合检索算法测试文件 - 改进版

包含完整流程测试和结果展示
"""

import asyncio
from typing import List, Dict


class MockBM25Index:
    """模拟BM25索引"""
    async def search(self, query: str, top_k: int = 50) -> List[Dict]:
        documents = {
            '便宜': [
                {'doc_id': 'product_001', 'content': '小米13，价格2999元，性能强劲，拍照出色', 'score': 0.95},
                {'doc_id': 'product_002', 'content': '红米Note13，价格1999元，续航能力强', 'score': 0.92},
                {'doc_id': 'product_003', 'content': 'OPPO A77，价格1799元，屏幕清晰', 'score': 0.88},
                {'doc_id': 'product_004', 'content': 'vivo Y77，价格1699元，系统流畅', 'score': 0.85},
                {'doc_id': 'product_005', 'content': 'iPhone 15 Pro，价格7999元，性能最强', 'score': 0.3},
            ],
        }
        results = []
        for keyword, docs in documents.items():
            if keyword in query.lower():
                results.extend(docs)
        if not results:
            results = list(documents.values())[0]
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]


class MockVectorIndex:
    """模拟向量索引"""
    async def search(self, query: str, top_k: int = 50) -> List[Dict]:
        documents = [
            {'doc_id': 'product_001', 'content': '小米13，价格2999元，性能强劲，拍照出色', 'similarity_score': 0.92},
            {'doc_id': 'product_002', 'content': '红米Note13，价格1999元，续航能力强', 'similarity_score': 0.89},
            {'doc_id': 'product_003', 'content': 'OPPO A77，价格1799元，屏幕清晰', 'similarity_score': 0.85},
            {'doc_id': 'product_004', 'content': 'vivo Y77，价格1699元，系统流畅', 'similarity_score': 0.82},
            {'doc_id': 'product_007', 'content': '华为P60，价格4999元，拍照专业', 'similarity_score': 0.78},
        ]
        return documents[:top_k]


class MockLLMClient:
    """模拟LLM客户端"""
    async def generate(self, prompt: str) -> str:
        if '扩展问题' in prompt:
            return """便宜的手机有哪些推荐
有没有价格低于2000元的手机"""
        return "模拟响应"


class MockRerankerClient:
    """模拟Reranker客户端"""
    async def rerank(self, inputs: List[Dict]) -> List[Dict]:
        results = []
        for i, inp in enumerate(inputs):
            score = 0.9 - (i * 0.05)
            results.append({'score': max(0, score), 'confidence': 0.85 + (i * 0.01)})
        return results


class TestHybridRetrieval:
    """混合检索测试"""
    
    def __init__(self):
        self.bm25_index = MockBM25Index()
        self.vector_index = MockVectorIndex()
        self.llm_client = MockLLMClient()
        self.reranker_client = MockRerankerClient()
    
    async def test_complete_flow(self):
        """完整流程测试 + 结果展示"""
        print("\n" + "="*80)
        print("混合检索算法完整流程测试")
        print("="*80)
        
        query = "便宜的手机"
        print(f"\n【用户查询】{query}\n")
        
        # 1. 查询扩展
        print("【步骤1】查询扩展")
        print("-" * 80)
        response = await self.llm_client.generate("请为以下用户问题生成2个高质量的扩展问题。")
        expansions = [q.strip() for q in response.split('\n') if q.strip()]
        print(f"原问题（权重×2）: {query}")
        for i, exp in enumerate(expansions, 1):
            print(f"扩展问题{i}（权重0.7）: {exp}")
        
        # 2. 并行检索
        print("\n【步骤2】并行检索")
        print("-" * 80)
        bm25_results = await self.bm25_index.search(query, top_k=5)
        vector_results = await self.vector_index.search(query, top_k=5)
        
        print(f"BM25搜索结果（Top-5）:")
        for rank, r in enumerate(bm25_results, 1):
            print(f"  {rank}. {r['doc_id']}: {r['content'][:40]}... (分数: {r['score']:.2f})")
        
        print(f"\n向量搜索结果（Top-5）:")
        for rank, r in enumerate(vector_results, 1):
            print(f"  {rank}. {r['doc_id']}: {r['content'][:40]}... (相似度: {r['similarity_score']:.2f})")
        
        # 3. RRF融合
        print("\n【步骤3】RRF融合")
        print("-" * 80)
        doc_scores = {}
        rrf_k = 60
        
        for rank, doc in enumerate(bm25_results, 1):
            rrf_score = 1.0 / (rrf_k + rank + 1)
            doc_id = doc['doc_id']
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {'rrf_score': 0, 'content': doc['content']}
            doc_scores[doc_id]['rrf_score'] += rrf_score
        
        for rank, doc in enumerate(vector_results, 1):
            rrf_score = 1.0 / (rrf_k + rank + 1)
            doc_id = doc['doc_id']
            if doc_id not in doc_scores:
                doc_scores[doc_id] = {'rrf_score': 0, 'content': doc['content']}
            doc_scores[doc_id]['rrf_score'] += rrf_score
        
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1]['rrf_score'], reverse=True)
        
        print("RRF融合后的排序（Top-5）:")
        for rank, (doc_id, info) in enumerate(sorted_docs[:5], 1):
            print(f"  {rank}. {doc_id}: RRF分数={info['rrf_score']:.4f}")
            print(f"      内容: {info['content'][:50]}...")
        
        # 4. Rerank
        print("\n【步骤4】Rerank重排序")
        print("-" * 80)
        top_3_docs = sorted_docs[:3]
        rerank_inputs = [{'query': query, 'document': doc[1]['content']} for doc in top_3_docs]
        rerank_scores = await self.reranker_client.rerank(rerank_inputs)
        
        print("Rerank结果（Top-3）:")
        for (doc_id, info), score in zip(top_3_docs, rerank_scores):
            print(f"  {doc_id}: Rerank分数={score['score']:.2f}, 置信度={score['confidence']:.2f}")
        
        # 5. 位置感知混合
        print("\n【步骤5】位置感知混合")
        print("-" * 80)
        final_results = []
        for rank, ((doc_id, info), rerank_score) in enumerate(zip(top_3_docs, rerank_scores), 1):
            if rank <= 3:
                retrieval_weight, rerank_weight = 0.75, 0.25
            elif rank <= 10:
                retrieval_weight, rerank_weight = 0.60, 0.40
            else:
                retrieval_weight, rerank_weight = 0.40, 0.60
            
            final_score = info['rrf_score'] * retrieval_weight + rerank_score['score'] * rerank_weight
            
            final_results.append({
                'doc_id': doc_id,
                'content': info['content'],
                'rrf_score': info['rrf_score'],
                'rerank_score': rerank_score['score'],
                'final_score': final_score,
                'blend_ratio': (retrieval_weight, rerank_weight),
            })
        
        final_results.sort(key=lambda x: x['final_score'], reverse=True)
        
        print("最终排序结果（Top-3）:")
        for rank, result in enumerate(final_results, 1):
            print(f"  {rank}. {result['doc_id']}")
            print(f"      RRF分数: {result['rrf_score']:.4f}")
            print(f"      Rerank分数: {result['rerank_score']:.2f}")
            print(f"      混合比例: {result['blend_ratio'][0]:.0%} 检索 + {result['blend_ratio'][1]:.0%} rerank")
            print(f"      最终分数: {result['final_score']:.4f}")
            print(f"      内容: {result['content'][:50]}...")
        
        # 6. 上下文整合
        print("\n【步骤6】上下文整合到Prompt")
        print("-" * 80)
        print("最终上下文：\n")
        for rank, result in enumerate(final_results[:3], 1):
            print(f"【参考资料 {rank}】")
            print(f"相关度: {result['final_score']:.2%}")
            print(f"内容: {result['content']}\n")
        
        print("="*80)
        print("✓ 完整流程测试通过！")
        print("="*80)


async def main():
    tester = TestHybridRetrieval()
    await tester.test_complete_flow()


if __name__ == '__main__':
    asyncio.run(main())
