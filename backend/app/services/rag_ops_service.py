from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

from app.core.config import settings
from app.repositories.base import RagOfflineJobRepository
from app.schemas.domain import RagOfflineJobRecord


class RagOpsService:
    def __init__(
        self,
        *,
        retrieval_pipeline,
        qa_agent,
        bm25_index,
        vector_index,
        rag_job_repository: RagOfflineJobRepository,
    ):
        self.retrieval_pipeline = retrieval_pipeline
        self.qa_agent = qa_agent
        self.bm25_index = bm25_index
        self.vector_index = vector_index
        self.rag_job_repository = rag_job_repository
        self.processes: dict[str, subprocess.Popen] = {}
        self.backend_dir = Path(__file__).resolve().parents[2]
        self.repo_root = self.backend_dir.parent
        self.logs_dir = self.backend_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    async def online_debug(
        self,
        *,
        query: str,
        current_product_id: str | None,
        live_stage: str,
        source_hint: str | None,
    ) -> dict[str, Any]:
        state = {
            "trace_id": "rag-debug",
            "session_id": "rag-debug",
            "user_id": "rag-debug",
            "user_input": query,
            "live_stage": live_stage,
            "current_product_id": current_product_id,
            "short_term_memory": [],
            "knowledge_scope": source_hint or "mixed",
        }

        rewrite_started = perf_counter()
        rewritten_query = await self.qa_agent._rewrite_query(state)
        rewrite_ms = int((perf_counter() - rewrite_started) * 1000)

        effective_source_hint = source_hint or self.retrieval_pipeline._infer_source_hint(rewritten_query)

        expand_started = perf_counter()
        expanded_queries = await self.retrieval_pipeline._expand_query(rewritten_query)
        expand_ms = int((perf_counter() - expand_started) * 1000)

        retrieve_started = perf_counter()
        all_results = await self.retrieval_pipeline._parallel_retrieve(expanded_queries)
        retrieve_ms = int((perf_counter() - retrieve_started) * 1000)

        fusion_started = perf_counter()
        fused_results = await self.retrieval_pipeline._rrf_fusion(all_results, effective_source_hint)
        fusion_ms = int((perf_counter() - fusion_started) * 1000)

        rerank_started = perf_counter()
        rerank_results = await self.retrieval_pipeline._rerank(rewritten_query, fused_results)
        rerank_results = self.retrieval_pipeline._apply_source_preference(rerank_results, effective_source_hint)
        rerank_ms = int((perf_counter() - rerank_started) * 1000)

        context = self.retrieval_pipeline._build_context(rerank_results)

        return {
            "query": query,
            "rewritten_query": rewritten_query,
            "source_hint": effective_source_hint,
            "expanded_queries": expanded_queries,
            "bm25_results": [
                {"query": item["query"], "results": item["bm25"][:5]}
                for item in all_results
            ],
            "vector_results": [
                {"query": item["query"], "results": item["vector"][:5]}
                for item in all_results
            ],
            "fused_results": [
                {
                    "doc_id": item.doc_id,
                    "fused_score": item.fused_score,
                    "rrf_rank": item.rrf_rank,
                    "source_type": item.source_type,
                    "source_bonus": item.source_bonus,
                    "content": item.content,
                }
                for item in fused_results[:10]
            ],
            "rerank_results": [
                {
                    "doc_id": item.doc_id,
                    "final_score": item.final_score,
                    "rerank_score": item.rerank_score,
                    "rrf_rank": item.rrf_rank,
                    "source_type": item.source_type,
                    "content": item.content,
                }
                for item in rerank_results[:10]
            ],
            "context": context,
            "timings_ms": {
                "rewrite": rewrite_ms,
                "expand": expand_ms,
                "retrieve": retrieve_ms,
                "fusion": fusion_ms,
                "rerank": rerank_ms,
            },
            "degraded": {
                "bm25": len(self._flatten_counts(all_results, "bm25")) == 0,
                "vector": len(self._flatten_counts(all_results, "vector")) == 0,
            },
        }

    async def get_offline_overview(self) -> dict[str, Any]:
        docs_dir = self.repo_root / "docs" / "data"
        source_files = [item for item in docs_dir.rglob("*") if item.is_file()] if docs_dir.exists() else []
        recent_jobs = await self.rag_job_repository.list_recent(limit=10)
        return {
            "docs_dir": str(docs_dir),
            "source_file_count": len(source_files),
            "bm25_count": self.bm25_index.count(),
            "vector_count": self.vector_index.count(),
            "upload_enabled": False,
            "recent_jobs": [self._job_payload(item) for item in recent_jobs],
        }

    async def start_offline_job(
        self,
        *,
        job_type: str,
        docs_dir: str | None,
        reset: bool = False,
        es_only: bool = False,
        milvus_only: bool = False,
    ) -> dict[str, Any]:
        docs_dir = docs_dir or str(self.repo_root / "docs" / "data")
        effective_reset = reset or job_type == "full"
        job = RagOfflineJobRecord(job_type=job_type, status="queued", docs_dir=docs_dir, args={
            "reset": effective_reset,
            "es_only": es_only,
            "milvus_only": milvus_only,
        })
        job = await self.rag_job_repository.create(job)

        script_path = self.backend_dir / "scripts" / "index_data.py"
        log_path = self.logs_dir / f"rag_job_{job.id}.log"
        command = [sys.executable, "-X", "utf8", str(script_path), "--docs-dir", docs_dir]
        if effective_reset:
            command.append("--reset")
        if es_only:
            command.append("--es-only")
        if milvus_only:
            command.append("--milvus-only")

        with open(log_path, "a", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                command,
                cwd=str(self.backend_dir),
                stdout=log_file,
                stderr=log_file,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )

        job.status = "running"
        job.log_path = str(log_path)
        job.pid = process.pid
        job = await self.rag_job_repository.save(job)
        self.processes[job.id] = process
        return self._job_payload(job)

    async def get_job_detail(self, job_id: str) -> dict[str, Any] | None:
        job = await self.rag_job_repository.get(job_id)
        if job is None:
            return None

        process = self.processes.get(job.id)
        if process is not None:
            return_code = process.poll()
            if return_code is not None and job.status == "running":
                job.status = "completed" if return_code == 0 else "failed"
                job.error_message = None if return_code == 0 else f"exit_code={return_code}"
                job = await self.rag_job_repository.save(job)

        payload = self._job_payload(job)
        payload["log_tail"] = self._tail_log(job.log_path, settings.OFFLINE_JOB_LOG_LINES)
        return payload

    def _job_payload(self, record: RagOfflineJobRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "job_type": record.job_type,
            "status": record.status,
            "docs_dir": record.docs_dir,
            "args": record.args,
            "log_path": record.log_path,
            "pid": record.pid,
            "error_message": record.error_message,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    def _tail_log(self, log_path: str | None, line_count: int) -> list[str]:
        if not log_path or not Path(log_path).exists():
            return []
        lines = Path(log_path).read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-line_count:]

    def _flatten_counts(self, all_results: list[dict[str, Any]], key: str) -> list[Any]:
        flattened: list[Any] = []
        for item in all_results:
            flattened.extend(item.get(key, []))
        return flattened
