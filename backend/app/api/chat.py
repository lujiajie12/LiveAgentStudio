import asyncio
import logging
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_container, get_current_user
from app.core.trace import get_trace_id
from app.schemas.chat import ChatEvent, ChatStreamRequest, SessionMessage
from app.schemas.common import ApiResponse
from app.schemas.auth import CurrentUser
from app.services.streaming_service import format_sse_event

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/chat/stream")
async def stream_chat(
    payload: ChatStreamRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    trace_id = getattr(request.state, "trace_id", None) or get_trace_id()
    t0 = time.perf_counter()
    logger.info(f"[TIMING][{trace_id}] request_received query='{payload.user_input[:50]}'")

    async def event_generator():
        try:
            t_meta = time.perf_counter()
            yield format_sse_event(
                ChatEvent(
                    event="meta",
                    data={
                        "trace_id": trace_id,
                        "session_id": payload.session_id,
                        "intent": "qa",
                        "pending": True,
                    },
                )
            )
            logger.info(f"[TIMING][{trace_id}] meta_pending_sent t={((time.perf_counter()-t0)*1000):.0f}ms")

            task = asyncio.create_task(
                container.chat_service.run_chat(
                    payload, current_user.id, trace_id, current_user.role.value
                )
            )

            while not task.done():
                await asyncio.sleep(5)
                if task.done():
                    break
                t_elapsed = (time.perf_counter() - t0) * 1000
                logger.info(f"[TIMING][{trace_id}] still_processing t={t_elapsed:.0f}ms")
                yield format_sse_event(
                    ChatEvent(
                        event="status",
                        data={
                            "trace_id": trace_id,
                            "session_id": payload.session_id,
                            "stage": "processing",
                            "message": f"系统正在分析问题并准备回答... ({int(t_elapsed/1000)}s)",
                        },
                    )
                )

            result, assistant_message = await task
            t_done = time.perf_counter()
            logger.info(f"[TIMING][{trace_id}] task_completed t={((t_done-t0)*1000):.0f}ms intent={result.get('intent')}")

            yield format_sse_event(
                ChatEvent(
                    event="meta",
                    data={
                        "trace_id": trace_id,
                        "session_id": payload.session_id,
                        "intent": result["intent"],
                        "agent_name": result.get("agent_name"),
                        "tool_intent": result.get("tool_intent"),
                        "planner_action": result.get("planner_action"),
                        "tools_used": result.get("tools_used", []),
                        "pending": False,
                    },
                )
            )
            logger.info(f"[TIMING][{trace_id}] meta_done_sent t={((time.perf_counter()-t0)*1000):.0f}ms")

            first_token_sent = False
            for chunk in container.streaming_service.chunk_text(result["final_output"]):
                if not first_token_sent:
                    t_first = time.perf_counter()
                    logger.info(f"[TIMING][{trace_id}] first_token_sent t={((t_first-t0)*1000):.0f}ms")
                    first_token_sent = True
                yield format_sse_event(ChatEvent(event="token", data={"content": chunk}))
                await asyncio.sleep(container.streaming_service.event_delay_ms / 1000)

            t_final = time.perf_counter()
            logger.info(f"[TIMING][{trace_id}] stream_done total={((t_final-t0)*1000):.0f}ms chunks={len(result.get('final_output',''))}")
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
            logger.error(f"[TIMING][{trace_id}] stream_error t={((time.perf_counter()-t0)*1000):.0f}ms error={exc}")
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
