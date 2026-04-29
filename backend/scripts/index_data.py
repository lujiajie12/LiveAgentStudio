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
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
from app.rag.query_constraints import extract_catalog_attributes
for _p in [
    # 索引脚本只读取 backend/.env，与应用主配置保持一致。
    os.path.normpath(os.path.join(BACKEND_DIR, '.env')),
    os.path.normpath(os.path.join(BACKEND_DIR, '..', '.env')),
]:
    if os.path.exists(_p):
        load_dotenv(_p)
        logger.info('Loaded env: %s', _p)
        break


MILVUS_COLLECTION_NAME = "knowledge_base"
MILVUS_REBUILD_PREFIX = f"{MILVUS_COLLECTION_NAME}_rebuild_"


async def _wait_for_milvus_collection_absent(
    host: str,
    port: int,
    collection_name: str,
    timeout_seconds: int = 45,
) -> None:
    from pymilvus import connections, utility

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            connections.connect(alias="default", host=host, port=port)
            if not utility.has_collection(collection_name):
                await asyncio.sleep(2.0)
                return
        except Exception as exc:
            logger.warning("Waiting for Milvus drop state failed once: %s", exc)
        await asyncio.sleep(1.0)

    raise RuntimeError(f"Milvus collection {collection_name} still exists after reset wait")


async def _wait_for_milvus_collection_ready(
    host: str,
    port: int,
    collection_name: str,
    timeout_seconds: int = 45,
) -> None:
    from pymilvus import Collection, connections, utility

    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            connections.connect(alias="default", host=host, port=port)
            if utility.has_collection(collection_name):
                collection = Collection(collection_name)
                _ = collection.num_entities
                await asyncio.sleep(2.0)
                return
        except Exception as exc:
            last_error = exc
            logger.warning("Waiting for Milvus ready state failed once: %s", exc)
        await asyncio.sleep(1.5)

    raise RuntimeError(
        f"Milvus collection {collection_name} not ready after create wait: {last_error}"
    )


async def _wait_for_milvus_entity_count(
    host: str,
    port: int,
    collection_name: str,
    target_count: int,
    timeout_seconds: int = 60,
) -> None:
    from pymilvus import Collection, connections

    deadline = time.time() + timeout_seconds
    last_count = None
    while time.time() < deadline:
        try:
            connections.connect(alias="default", host=host, port=port)
            collection = Collection(collection_name)
            count = int(collection.num_entities)
            last_count = count
            if count == target_count:
                await asyncio.sleep(1.5)
                return
        except Exception as exc:
            logger.warning("Waiting for Milvus entity count failed once: %s", exc)
        await asyncio.sleep(1.5)

    raise RuntimeError(
        f"Milvus collection {collection_name} entity count did not reach {target_count}, "
        f"last_count={last_count}"
    )


async def _wait_for_milvus_write_path_stable(
    host: str,
    port: int,
    collection_name: str,
    settle_seconds: int = 10,
) -> None:
    from pymilvus import Collection, connections

    deadline = time.time() + settle_seconds
    last_error = None
    while time.time() < deadline:
        try:
            connections.connect(alias="default", host=host, port=port)
            collection = Collection(collection_name)
            _ = collection.schema
            _ = collection.num_entities
            last_error = None
        except Exception as exc:
            last_error = exc
            logger.warning("Milvus write path still stabilizing: %s", exc)
        await asyncio.sleep(1.0)

    if last_error is not None:
        logger.warning(
            "Milvus write path did not become fully quiet before timeout, proceeding cautiously: %s",
            last_error,
        )


def _build_rebuild_collection_name() -> str:
    return f"{MILVUS_REBUILD_PREFIX}{int(time.time())}"


PRODUCT_TITLE_PATTERN = re.compile(
    r"^\s*#+\s*(?P<name>[^()\n（]+?)\s*[（(](?P<sku>[^()（）\n]+)[)）]",
    re.MULTILINE,
)


def _extract_search_fields(doc) -> dict:
    metadata = dict(getattr(doc, "metadata", {}) or {})
    text = str(getattr(doc, "page_content", "") or "")[:4000]
    section_title = str(metadata.get("section_title", "") or "").strip()
    subsection_title = str(metadata.get("subsection_title", "") or "").strip()
    source_file = str(metadata.get("source_file", "") or "").strip()

    # 商品详情 markdown 会把标题写成“# 商品名（SKU）”，这里在建索引阶段抽出来做结构化字段，
    # 这样商品名、SKU、标题命中时可以单独加权，而不是和长正文完全混在一起。
    title_source = section_title or subsection_title or text
    title_match = PRODUCT_TITLE_PATTERN.search(title_source)
    product_name = str(metadata.get("product_name", "") or "").strip() or (
        title_match.group("name").strip() if title_match else ""
    )
    sku = str(metadata.get("sku", "") or "").strip() or (
        title_match.group("sku").strip() if title_match else ""
    )
    catalog_attributes = extract_catalog_attributes(text, metadata)

    # search_text 是给 BM25 的聚合检索字段，专门把标题、商品名、SKU 和正文拼起来。
    search_text = " ".join(
        part
        for part in [
            section_title,
            subsection_title,
            product_name,
            sku,
            catalog_attributes.get("category", ""),
            catalog_attributes.get("product_type", ""),
            catalog_attributes.get("price_band_text", ""),
            source_file,
            text,
        ]
        if str(part).strip()
    )

    return {
        "text": text,
        "chunk_id": str(metadata.get("chunk_id", "") or ""),
        "source_file": source_file,
        "section_title": section_title,
        "subsection_title": subsection_title,
        "product_name": product_name,
        "sku": sku,
        "category": str(catalog_attributes.get("category", "") or ""),
        "audience": str(catalog_attributes.get("audience", "") or ""),
        "product_type": str(catalog_attributes.get("product_type", "") or ""),
        "price_band_text": str(catalog_attributes.get("price_band_text", "") or ""),
        "price_band_low": catalog_attributes.get("price_band_low"),
        "price_band_high": catalog_attributes.get("price_band_high"),
        "search_text": search_text,
        "metadata": {k: str(v) for k, v in metadata.items()},
    }


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
            settings={
                'number_of_shards': 1,
                'number_of_replicas': 0,
                'analysis': {
                    'normalizer': {
                        'lowercase_normalizer': {
                            'type': 'custom',
                            'filter': ['lowercase', 'asciifolding'],
                        }
                    },
                    'analyzer': {
                        # 不依赖第三方 IK 插件，直接用 ES 内置 cjk_bigram 做中文商品名/自然问句召回。
                        'zh_cjk_analyzer': {
                            'tokenizer': 'standard',
                            'filter': ['cjk_width', 'lowercase', 'cjk_bigram'],
                        }
                    },
                },
            },
            mappings={'properties': {
                'text': {
                    'type': 'text',
                    'analyzer': 'zh_cjk_analyzer',
                    'search_analyzer': 'zh_cjk_analyzer',
                    'fields': {
                        'std': {'type': 'text', 'analyzer': 'standard'},
                    },
                },
                'search_text': {
                    'type': 'text',
                    'analyzer': 'zh_cjk_analyzer',
                    'search_analyzer': 'zh_cjk_analyzer',
                },
                'section_title': {
                    'type': 'text',
                    'analyzer': 'zh_cjk_analyzer',
                    'search_analyzer': 'zh_cjk_analyzer',
                    'fields': {
                        'keyword': {'type': 'keyword', 'ignore_above': 512},
                    },
                },
                'subsection_title': {
                    'type': 'text',
                    'analyzer': 'zh_cjk_analyzer',
                    'search_analyzer': 'zh_cjk_analyzer',
                },
                'product_name': {
                    'type': 'text',
                    'analyzer': 'zh_cjk_analyzer',
                    'search_analyzer': 'zh_cjk_analyzer',
                    'fields': {
                        'keyword': {'type': 'keyword', 'ignore_above': 512},
                    },
                },
                'category': {
                    'type': 'text',
                    'analyzer': 'zh_cjk_analyzer',
                    'search_analyzer': 'zh_cjk_analyzer',
                },
                'audience': {
                    'type': 'text',
                    'analyzer': 'zh_cjk_analyzer',
                    'search_analyzer': 'zh_cjk_analyzer',
                },
                'product_type': {
                    'type': 'text',
                    'analyzer': 'zh_cjk_analyzer',
                    'search_analyzer': 'zh_cjk_analyzer',
                    'fields': {
                        'keyword': {'type': 'keyword', 'ignore_above': 512},
                    },
                },
                'price_band_text': {
                    'type': 'keyword',
                    'ignore_above': 128,
                },
                'price_band_low': {'type': 'integer'},
                'price_band_high': {'type': 'integer'},
                'sku': {
                    'type': 'keyword',
                    'normalizer': 'lowercase_normalizer',
                },
                'chunk_id': {'type': 'keyword'},
                'source_file': {'type': 'keyword'},
                # metadata 只保留原始信息用于排障/展示，不参与 BM25 建模，避免动态字段膨胀。
                'metadata': {'type': 'object', 'enabled': False},
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
                '_source': _extract_search_fields(d)
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
    from pymilvus import Collection, connections, utility

    target_collection_name = MILVUS_COLLECTION_NAME
    if reset:
        target_collection_name = _build_rebuild_collection_name()
        logger.info(
            "Reset requested, indexing into fresh Milvus collection first: %s",
            target_collection_name,
        )

    if reset:
        try:
            connections.connect(host=host, port=port)
            if utility.has_collection(MILVUS_COLLECTION_NAME):
                logger.info(
                    'Keeping current Milvus collection intact until rebuild succeeds: %s',
                    MILVUS_COLLECTION_NAME,
                )
        except Exception as e:
            logger.warning('Failed to inspect current Milvus collection before rebuild: %s', e)

    skip = 0
    try:
        connections.connect(host=host, port=port)
        if utility.has_collection(target_collection_name):
            n = Collection(target_collection_name).num_entities
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
    vector_store = MilvusVectorStore(
        host=host,
        port=port,
        collection_name=target_collection_name,
    )
    await vector_store.connect()
    await vector_store.create_collection()
    await _wait_for_milvus_collection_ready(host, port, target_collection_name)
    if reset:
        logger.info('Waiting for Milvus DML channel to stabilize after reset...')
        await _wait_for_milvus_write_path_stable(
            host,
            port,
            target_collection_name,
            settle_seconds=settings.MILVUS_RESET_SETTLE_SECONDS,
        )
        await asyncio.sleep(2.0)

    logger.info('Vectorizing %d chunks with %s (skip=%d)...', len(docs), settings.EMBEDDING_MODEL, skip)
    t0 = time.time()

    # 小批次 embed + 大窗口 flush，避免 reset 后每批都 flush 把 Milvus 写通道打爆。
    batch_size = settings.EMBEDDING_BATCH_SIZE
    flush_interval_chunks = max(batch_size, int(settings.MILVUS_INDEX_FLUSH_INTERVAL_CHUNKS or batch_size))
    total = skip
    pending_flush_count = 0

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
        await vector_store.insert_chunks(chunks, embeddings, flush=False)
        total += len(batch)
        pending_flush_count += len(batch)
        if pending_flush_count >= flush_interval_chunks:
            logger.info(
                'Milvus flushing buffered vectors: pending=%d total=%d collection=%s',
                pending_flush_count,
                total,
                target_collection_name,
            )
            await vector_store.flush(expected_min_entities=total)
            await _wait_for_milvus_entity_count(host, port, target_collection_name, total, timeout_seconds=120)
            pending_flush_count = 0
        logger.info('Milvus progress: %d/%d (%.1f vecs/s)',
                    total, len(docs), total / max(time.time() - t0, 0.001))

    if total > skip:
        logger.info('Milvus final flush: total=%d collection=%s', total, target_collection_name)
        await vector_store.flush(expected_min_entities=total)
        await _wait_for_milvus_entity_count(host, port, target_collection_name, total, timeout_seconds=180)

    if reset and target_collection_name != MILVUS_COLLECTION_NAME:
        logger.info(
            "Milvus rebuild finished in temp collection %s, swapping into %s",
            target_collection_name,
            MILVUS_COLLECTION_NAME,
        )
        try:
            Collection(target_collection_name).release()
        except Exception:
            pass
        try:
            connections.disconnect(alias="default")
        except Exception:
            pass
        await asyncio.sleep(2.0)
        connections.connect(host=host, port=port)
        if utility.has_collection(MILVUS_COLLECTION_NAME):
            logger.info("Dropping old Milvus collection before rename: %s", MILVUS_COLLECTION_NAME)
            utility.drop_collection(MILVUS_COLLECTION_NAME)
            await _wait_for_milvus_collection_absent(host, port, MILVUS_COLLECTION_NAME)
        utility.rename_collection(target_collection_name, MILVUS_COLLECTION_NAME)
        await _wait_for_milvus_collection_ready(host, port, MILVUS_COLLECTION_NAME)
        logger.info("Milvus collection swap complete: %s", MILVUS_COLLECTION_NAME)

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
