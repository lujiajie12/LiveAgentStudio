from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.dependencies import get_container, get_current_user
from app.core.websocket_auth import authenticate_websocket
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/teleprompter", tags=["teleprompter"])


class TeleprompterPushRequest(BaseModel):
    session_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=5000)
    source_agent: str = Field(default="qa", min_length=1, max_length=64)
    priority: str = Field(default="normal", min_length=1, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/push", response_model=ApiResponse)
async def push_to_teleprompter(
    payload: TeleprompterPushRequest,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    result = await container.teleprompter_service.push(
        session_id=payload.session_id,
        title=payload.title,
        content=payload.content,
        source_agent=payload.source_agent,
        priority=payload.priority,
        requested_by=current_user.id,
        metadata=payload.metadata,
    )
    return ApiResponse(data=result)


@router.get("/current", response_model=ApiResponse)
async def get_current_teleprompter(
    session_id: str = Query(..., min_length=1),
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    result = await container.teleprompter_service.get_current(session_id)
    return ApiResponse(data=result)


@router.websocket("/stream")
async def teleprompter_stream(websocket: WebSocket):
    container = websocket.app.state.container
    user = await authenticate_websocket(websocket, container)
    if user is None:
        return

    session_id = websocket.query_params.get("session_id")
    if not session_id:
        await websocket.close(code=4400, reason="Missing session_id")
        return

    await websocket.accept()
    current = await container.teleprompter_service.get_current(session_id)
    await websocket.send_json({"type": "snapshot", "item": current, "session_id": session_id})

    queue = await container.teleprompter_service.subscribe(session_id)
    try:
        while True:
            payload = await queue.get()
            payload["session_id"] = session_id
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        await container.teleprompter_service.unsubscribe(session_id, queue)
