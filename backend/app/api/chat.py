from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_container, get_current_user
from app.core.trace import get_trace_id
from app.schemas.chat import ChatEvent, ChatStreamRequest, SessionMessage
from app.schemas.common import ApiResponse
from app.schemas.auth import CurrentUser
from app.services.streaming_service import format_sse_event

router = APIRouter(tags=["chat"])


@router.post("/chat/stream")
async def stream_chat(
    payload: ChatStreamRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()

    async def event_generator():
        try:
            result, assistant_message = await container.chat_service.run_chat(
                payload, current_user.id, trace_id, current_user.role.value
            )
            yield format_sse_event(
                ChatEvent(
                    event="meta",
                    data={
                        "trace_id": trace_id,
                        "session_id": payload.session_id,
                        "intent": result["intent"],
                    },
                )
            )
            for chunk in container.streaming_service.chunk_text(result["final_output"]):
                yield format_sse_event(ChatEvent(event="token", data={"content": chunk}))
            yield format_sse_event(
                ChatEvent(
                    event="final",
                    data={
                        "message": SessionMessage.model_validate(assistant_message.model_dump()).model_dump(
                            mode="json"
                        ),
                        "intent": result["intent"],
                        "guardrail_pass": result["guardrail_pass"],
                    },
                )
            )
        except Exception as exc:
            yield format_sse_event(
                ChatEvent(
                    event="error",
                    data={"message": str(exc), "trace_id": trace_id},
                )
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sessions/{session_id}/messages", response_model=ApiResponse)
async def get_messages(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    messages = await container.message_repository.list_by_session(session_id)
    payload = [SessionMessage.model_validate(item.model_dump()).model_dump(mode="json") for item in messages]
    return ApiResponse(data=payload)
