from pydantic import BaseModel
from fastapi import APIRouter, Depends

from app.core.dependencies import get_container, get_current_user
from app.core.exceptions import AppError
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/rag", tags=["rag"])


class RagOnlineDebugRequest(BaseModel):
    query: str
    current_product_id: str | None = None
    live_stage: str = "warmup"
    source_hint: str | None = None


class RagOfflineJobRequest(BaseModel):
    job_type: str = "incremental"
    docs_dir: str | None = None
    reset: bool = False
    es_only: bool = False
    milvus_only: bool = False


@router.post("/online/debug", response_model=ApiResponse)
async def rag_online_debug(
    payload: RagOnlineDebugRequest,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    result = await container.rag_ops_service.online_debug(
        query=payload.query,
        current_product_id=payload.current_product_id,
        live_stage=payload.live_stage,
        source_hint=payload.source_hint,
    )
    return ApiResponse(data=result)


@router.get("/offline/overview", response_model=ApiResponse)
async def rag_offline_overview(
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    return ApiResponse(data=await container.rag_ops_service.get_offline_overview())


@router.post("/offline/jobs", response_model=ApiResponse)
async def create_rag_offline_job(
    payload: RagOfflineJobRequest,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    job = await container.rag_ops_service.start_offline_job(
        job_type=payload.job_type,
        docs_dir=payload.docs_dir,
        reset=payload.reset,
        es_only=payload.es_only,
        milvus_only=payload.milvus_only,
    )
    return ApiResponse(data=job)


@router.get("/offline/jobs/{job_id}", response_model=ApiResponse)
async def get_rag_offline_job(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    job = await container.rag_ops_service.get_job_detail(job_id)
    if job is None:
        raise AppError("rag_job_not_found", "RAG offline job does not exist", 404)
    return ApiResponse(data=job)
