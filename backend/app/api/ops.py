from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_container, get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/ops", tags=["ops"])


class TTSBroadcastRequest(BaseModel):
    session_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field(default="xiaoyun", min_length=1, max_length=64)


@router.get("/traces", response_model=ApiResponse)
async def list_traces(
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    traces = await container.ops_service.list_recent_traces(limit=limit)
    return ApiResponse(data=traces)


@router.get("/traces/{trace_id}", response_model=ApiResponse)
async def get_trace_detail(
    trace_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    detail = await container.ops_service.get_trace_detail(trace_id)
    return ApiResponse(data=detail)


@router.get("/priority-queue", response_model=ApiResponse)
async def get_priority_queue(
    session_id: str = Query(..., min_length=1),
    limit: int = Query(3, ge=1, le=10),
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    queue = await container.ops_service.get_priority_queue(session_id=session_id, limit=limit)
    return ApiResponse(data=queue)


@router.get("/action-center", response_model=ApiResponse)
async def get_action_center(
    session_id: str = Query(..., min_length=1),
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    payload = await container.ops_service.get_action_center(session_id=session_id)
    return ApiResponse(data=payload)


@router.post("/tts/broadcast", response_model=ApiResponse)
async def broadcast_tts(
    payload: TTSBroadcastRequest,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    result = await container.ops_service.broadcast_tts(
        session_id=payload.session_id,
        text=payload.text,
        voice=payload.voice,
        requested_by=current_user.id,
    )
    return ApiResponse(data=result)
