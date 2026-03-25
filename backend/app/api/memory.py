from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_container, get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(tags=["memory"])


@router.get("/sessions/{session_id}/memory", response_model=ApiResponse)
async def get_session_memory(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    snapshot = await container.memory_service.get_memory_snapshot(session_id)
    return ApiResponse(data=snapshot)


@router.get("/memory/high-frequency-questions", response_model=ApiResponse)
async def list_high_frequency_questions(
    product_id: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    records = await container.high_frequency_repository.list_by_product(product_id, limit=limit)
    return ApiResponse(data=[item.model_dump(mode="json") for item in records])
