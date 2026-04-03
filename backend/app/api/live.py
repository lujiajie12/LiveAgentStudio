from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.dependencies import get_container, get_current_user
from app.core.websocket_auth import authenticate_websocket
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/live", tags=["live"])


class BarrageIngestRequest(BaseModel):
    session_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="simulator", min_length=1, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)
    created_at: datetime | None = None
    current_product_id: str | None = Field(default=None, max_length=64)
    live_stage: str | None = Field(default=None, max_length=32)
    online_viewers: int | None = Field(default=None, ge=0)
    conversion_rate: float | None = Field(default=None, ge=0.0, le=100.0)
    interaction_rate: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveOverviewUpdateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    current_product_id: str | None = Field(default=None, max_length=64)
    live_stage: str | None = Field(default=None, max_length=32)
    online_viewers: int | None = Field(default=None, ge=0)
    conversion_rate: float | None = Field(default=None, ge=0.0, le=100.0)
    interaction_rate: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/barrages/ingest", response_model=ApiResponse)
async def ingest_barrage(
    payload: BarrageIngestRequest,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    record = await container.live_barrage_service.ingest_barrage(
        session_id=payload.session_id,
        display_name=payload.display_name,
        text=payload.text,
        source=payload.source,
        requested_by=current_user.id,
        user_id=payload.user_id,
        created_at=payload.created_at,
        current_product_id=payload.current_product_id,
        live_stage=payload.live_stage,
        online_viewers=payload.online_viewers,
        conversion_rate=payload.conversion_rate,
        interaction_rate=payload.interaction_rate,
        metadata=payload.metadata,
    )
    return ApiResponse(data=record)


@router.get("/overview", response_model=ApiResponse)
async def get_live_overview(
    session_id: str = Query(..., min_length=1),
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    overview = await container.live_barrage_service.get_overview(session_id)
    return ApiResponse(data=overview)


@router.post("/overview/update", response_model=ApiResponse)
async def update_live_overview(
    payload: LiveOverviewUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    overview = await container.live_barrage_service.update_overview(
        session_id=payload.session_id,
        requested_by=current_user.id,
        current_product_id=payload.current_product_id,
        live_stage=payload.live_stage,
        online_viewers=payload.online_viewers,
        conversion_rate=payload.conversion_rate,
        interaction_rate=payload.interaction_rate,
        metadata=payload.metadata,
    )
    return ApiResponse(data=overview)


@router.websocket("/barrages/stream")
async def barrage_stream(websocket: WebSocket):
    container = websocket.app.state.container
    user = await authenticate_websocket(websocket, container)
    if user is None:
        return

    session_id = websocket.query_params.get("session_id")
    if not session_id:
        await websocket.close(code=4400, reason="Missing session_id")
        return

    await websocket.accept()
    recent = await container.live_barrage_service.list_recent_barrages(session_id)
    overview = await container.live_barrage_service.get_overview(session_id)
    await websocket.send_json({"type": "snapshot", "items": recent, "session_id": session_id})
    await websocket.send_json({"type": "overview", "item": overview, "session_id": session_id})

    queue = await container.live_barrage_service.subscribe(session_id)
    try:
        while True:
            payload = await queue.get()
            payload["session_id"] = session_id
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        await container.live_barrage_service.unsubscribe(session_id, queue)
