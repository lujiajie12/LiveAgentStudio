#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
知识库索引化脚本 - LangChain 标准工具链

流程:
  文档目录 => DocumentLoader(按类型) => TextSplitter
           => BGEEmbeddings => Milvus(向量) + ES(BM25)

用法:
  python scripts/index_data.py --docs-dir /path/to/docs
  python scripts/index_data.py --es-only
  python scripts/index_data.py --milvus-only
  python scripts/index_data.py --reset
"""
import sys
import os
import argparse
import logging
import time
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
for _p in [
    os.path.normpath(os.path.join(BACKEND_DIR, '..', 'deploy', '.env')),
    os.path.normpath(os.path.join(BACKEND_DIR, '.env')),
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        logger.info('Loaded env: %s', _p)
        break


# ---------------------------------------------------------------------------
# BM25 索引 - ES 原生 bulk API
# ---------------------------------------------------------------------------

def index_elasticsearch(docs, host='localhost', port=9200, reset=False):
    from elasticsearch import Elasticsearch
    from elasticsearch.helpers import bulk

    es_url = f'http://{host}:{port}'
    index_name = 'knowledge_base'
    es = Elasticsearch(es_url, request_timeout=60)

    if reset:
        try:
            es.indices.delete(index=index_name, ignore_unavailable=True)
            logger.info('Deleted ES index')
        except Exception as e:
            logger.warning('Delete failed: %s', e)

    if not es.indices.exists(index=index_name):
        es.indices.create(
            index=index_name,
            settings={'number_of_shards': 1, 'number_of_replicas': 0},
            mappings={'properties': {
                'text':        {'type': 'text'},
                'chunk_id':    {'type': 'keyword'},
                'source_file': {'type': 'keyword'},
            }}
        )
        logger.info('Created ES index: %s', index_name)

    try:
        count = es.count(index=index_name).get('count', 0)
        if count > 0 and not reset:
            logger.info('ES already has %d docs, skip (--reset to reindex)', count)
            return count
    except:
        pass

    logger.info('Writing %d docs to ES via native bulk API...', len(docs))
    t0 = time.time()
    batch_size = 64
    total = 0

    for i in range(0, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        actions = [
            {
                '_index': index_name,
                '_source': {
                    'text':        d.page_content[:2000],
                    'chunk_id':    d.metadata.get('chunk_id', ''),
                    'source_file': d.metadata.get('source_file', ''),
                    'metadata':    {k: str(v) for k, v in d.metadata.items()},
                }
            }
            for d in batch
        ]
        try:
            success, _ = bulk(es, actions, request_timeout=60, max_retries=3,
                              initial_backoff=2, max_backoff=10)
            total += success
        except Exception as e:
            logger.error('Bulk error at batch %d: %s, retrying...', i, e)
            time.sleep(5)
            try:
                success, _ = bulk(es, actions, request_timeout=60)
                total += success
            except Exception as e2:
                logger.error('Batch %d failed permanently: %s', i, e2)
                continue

        if total % 500 == 0 or i + batch_size >= len(docs):
            logger.info('ES progress: %d/%d', total, len(docs))
            es.indices.refresh(index=index_name)

    logger.info('ES done: %d docs in %.1fs', total, time.time() - t0)
    return total


# ---------------------------------------------------------------------------
# 向量索引 - BGEEmbeddingModel + MilvusVectorStore
# ---------------------------------------------------------------------------

async def index_milvus_async(docs, host='localhost', port=19530, reset=False):
    from app.rag.embedding import BGEEmbeddingModel, MilvusVectorStore
    from app.schemas.document import DocumentChunk

    if reset:
        try:
            from pymilvus import utility, connections
            connections.connect(host=host, port=port)
            if utility.has_collection('knowledge_base'):
                utility.drop_collection('knowledge_base')
                logger.info('Dropped Milvus collection')
        except Exception as e:
            logger.warning('Drop failed: %s', e)

    skip = 0
    try:
        from pymilvus import Collection, utility, connections
        connections.connect(host=host, port=port)
        if utility.has_collection('knowledge_base'):
            n = Collection('knowledge_base').num_entities
            if n > 0 and not reset:
                if n >= len(docs):
                    logger.info('Milvus already has %d vectors, skip', n)
                    return n
                else:
                    logger.info('Milvus has %d/%d vectors, resuming from %d...', n, len(docs), n)
                    skip = n
    except:
        skip = 0

    from app.core.config import settings

    embed_model = BGEEmbeddingModel(
        device=settings.EMBEDDING_DEVICE,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
    )
    vector_store = MilvusVectorStore(host=host, port=port)
    await vector_store.connect()
    await vector_store.create_collection()

    from app.core.config import settings
    logger.info('Vectorizing %d chunks with %s (skip=%d)...', len(docs), settings.EMBEDDING_MODEL, skip)
    t0 = time.time()

    # 小批次 + content 截短，避免 gRPC 64MB 限制
    batch_size = settings.EMBEDDING_BATCH_SIZE
    total = skip

    for i in range(skip, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        texts = [d.page_content[:512] for d in batch]
        embeddings = await embed_model.embed_texts(texts)

        chunks = [
            DocumentChunk(
                chunk_id=str(d.metadata.get('chunk_id', f'chunk_{i+j}')),
                document_id=str(d.metadata.get('source_file', 'unknown')),
                chunk_index=i + j,
                content=d.page_content[:2000],  # 截短避免 gRPC 超限
                token_count=len(d.page_content),
                metadata=d.metadata,
            )
            for j, d in enumerate(batch)
        ]
        await vector_store.insert_chunks(chunks, embeddings)
        total += len(batch)
        logger.info('Milvus progress: %d/%d (%.1f vecs/s)',
                    total, len(docs), total / max(time.time() - t0, 0.001))

    logger.info('Milvus done: %d vectors in %.1fs', total, time.time() - t0)
    return total


def index_milvus(docs, host='localhost', port=19530, reset=False):
    return asyncio.run(index_milvus_async(docs, host, port, reset))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Index docs to ES(BM25) + Milvus(Vector)')
    parser.add_argument('--docs-dir',      default=None,  help='原始文档目录')
    parser.add_argument('--parent-child',  action='store_true')
    parser.add_argument('--chunk-size',    type=int, default=512)
    parser.add_argument('--chunk-overlap', type=int, default=128)
    parser.add_argument('--es-only',       action='store_true')
    parser.add_argument('--milvus-only',   action='store_true')
    parser.add_argument('--reset',         action='store_true')
    parser.add_argument('--es-host',       default='localhost')
    parser.add_argument('--es-port',       type=int, default=9200)
    parser.add_argument('--milvus-host',   default='localhost')
    parser.add_argument('--milvus-port',   type=int, default=19530)
    args = parser.parse_args()

    if args.docs_dir:
        from app.rag.document_pipeline import load_directory
        logger.info('Loading from %s (parent_child=%s)...', args.docs_dir, args.parent_child)
        child_docs, parent_docs = load_directory(
            args.docs_dir,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            use_parent_child=args.parent_child,
        )
        index_docs = bm25_docs = child_docs
        logger.info('child=%d parent=%d', len(child_docs), len(parent_docs))
    else:
        import glob, json
        from langchain_core.documents import Document
        kb_dir = os.path.join(BACKEND_DIR, 'kb_output')
        files = glob.glob(os.path.join(kb_dir, '*.jsonl'))
        if not files:
            logger.error('No --docs-dir and no JSONL in %s', kb_dir)
            sys.exit(1)
        latest = max(files, key=os.path.getmtime)
        logger.info('Fallback JSONL: %s', os.path.basename(latest))
        raw = []
        with open(latest, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try: raw.append(json.loads(line))
                    except: pass
        index_docs = bm25_docs = [
            Document(
                page_content=c['content'],
                metadata={
                    'chunk_id':    c['chunk_id'],
                    'source_file': c.get('source_file', ''),
                    **c.get('metadata', {}),
                }
            )
            for c in raw
        ]
        logger.info('Loaded %d chunks from JSONL', len(index_docs))

    print('\n' + '='*60)
    print('Knowledge Base Indexing')
    print('='*60)
    print(f'Docs:    {len(index_docs)} chunks')
    print(f'ES:      {args.es_host}:{args.es_port}')
    print(f'Milvus:  {args.milvus_host}:{args.milvus_port}')
    print(f'Reset:   {args.reset}')
    print('='*60 + '\n')

    if not args.milvus_only:
        print('[1/2] Elasticsearch BM25...')
        n = index_elasticsearch(bm25_docs, args.es_host, args.es_port, args.reset)
        print(f'[OK] ES: {n} docs\n')

    if not args.es_only:
        print('[2/2] Milvus Vector...')
        n = index_milvus(index_docs, args.milvus_host, args.milvus_port, args.reset)
        print(f'[OK] Milvus: {n} vectors\n')

    print('='*60)
    print('[DONE]')
    print('='*60)


if __name__ == '__main__':
    main()
