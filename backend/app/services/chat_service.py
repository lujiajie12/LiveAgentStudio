from app.graph.runtime import GraphRuntime
from app.repositories.base import MessageRepository, SessionRepository, ToolCallLogRepository
from app.schemas.chat import ChatStreamRequest
from app.schemas.domain import MessageRecord, MessageRole, SessionRecord
from app.schemas.domain import IntentType
from app.schemas.domain import SessionStatus
from app.schemas.domain import ToolCallLogRecord
from app.services.memory_service import MemoryService


class ChatService:
    def __init__(
        self,
        graph_runtime: GraphRuntime,
        session_repository: SessionRepository,
        message_repository: MessageRepository,
        memory_service: MemoryService,
        tool_log_repository: ToolCallLogRepository,
    ):
        self.graph_runtime = graph_runtime
        self.session_repository = session_repository
        self.message_repository = message_repository
        self.memory_service = memory_service
        self.tool_log_repository = tool_log_repository

    async def ensure_session(self, session_id: str, user_id: str) -> SessionRecord:
        session = await self.session_repository.get(session_id)
        if session is None:
            session = SessionRecord(id=session_id, user_id=user_id, status=SessionStatus.active)
            await self.session_repository.save(session)
        return session

    async def persist_user_message(self, session_id: str, content: str) -> MessageRecord:
        message = MessageRecord(
            session_id=session_id,
            role=MessageRole.user,
            content=content,
        )
        return await self.message_repository.create(message)

    async def persist_assistant_message(
        self,
        session_id: str,
        content: str,
        intent: str,
        metadata: dict,
    ) -> MessageRecord:
        message = MessageRecord(
            session_id=session_id,
            role=MessageRole.assistant,
            content=content,
            intent=IntentType(intent),
            agent_name=metadata.get("agent_name"),
            metadata=metadata,
        )
        return await self.message_repository.create(message)

    async def run_chat(
        self,
        request: ChatStreamRequest,
        user_id: str,
        trace_id: str,
    ) -> tuple[dict, MessageRecord]:
        session = await self.ensure_session(request.session_id, user_id)
        session.current_product_id = request.current_product_id
        session.live_stage = request.live_stage
        await self.session_repository.save(session)
        short_term_memory = await self.memory_service.get_short_term_memory(request.session_id)
        await self.persist_user_message(request.session_id, request.user_input)
        state = {
            "trace_id": trace_id,
            "session_id": request.session_id,
            "user_id": user_id,
            "user_input": request.user_input,
            "live_stage": request.live_stage.value,
            "current_product_id": request.current_product_id,
            "short_term_memory": short_term_memory,
        }
        result = await self.graph_runtime.ainvoke(state)

        assistant = await self.persist_assistant_message(
            session_id=request.session_id,
            content=result["final_output"],
            intent=result["intent"],
            metadata={
                "agent_name": result.get("agent_name"),
                "guardrail_pass": result.get("guardrail_pass"),
                "route_reason": result.get("route_reason"),
            },
        )
        await self.tool_log_repository.create(
            ToolCallLogRecord(
                session_id=request.session_id,
                tool_name="graph_runtime",
                input_payload={
                    "trace_id": trace_id,
                    "session_id": request.session_id,
                    "intent": result.get("intent"),
                },
                output_summary=result.get("final_output"),
                status="ok",
            )
        )
        return result, assistant
