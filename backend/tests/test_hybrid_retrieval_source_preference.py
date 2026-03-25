from app.rag.hybrid_retrieval_pipeline import HybridRetrievalPipeline, RerankResult


class DummyLLM:
    _client = None


class DummyIndex:
    async def search(self, query: str, top_k: int = 50):
        _ = query, top_k
        return []


class DummyReranker:
    async def rerank(self, inputs):
        _ = inputs
        return []


def build_pipeline() -> HybridRetrievalPipeline:
    return HybridRetrievalPipeline(
        llm_client=DummyLLM(),
        bm25_index=DummyIndex(),
        vector_index=DummyIndex(),
        reranker_client=DummyReranker(),
        n_expansions=0,
    )


def test_source_preference_moves_product_detail_ahead_of_faq():
    pipeline = build_pipeline()
    rerank_results = [
        RerankResult(
            doc_id="faq-1",
            content="faq",
            rrf_score=0.5,
            rrf_rank=1,
            rerank_score=0.95,
            rerank_confidence=0.9,
            final_score=0.95,
            blend_ratio=(0.6, 0.4),
            source_type="faq",
            source_bonus=0.0,
            metadata={},
        ),
        RerankResult(
            doc_id="detail-1",
            content="detail",
            rrf_score=0.3,
            rrf_rank=5,
            rerank_score=0.7,
            rerank_confidence=0.8,
            final_score=0.7,
            blend_ratio=(0.6, 0.4),
            source_type="product_detail",
            source_bonus=0.0,
            metadata={},
        ),
    ]

    ordered = pipeline._apply_source_preference(rerank_results, "product_detail")

    assert ordered[0].doc_id == "detail-1"
