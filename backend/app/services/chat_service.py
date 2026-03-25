from __future__ import annotations

from app.core.observability import bind_observability
from app.graph.runtime import GraphRuntime
from app.repositories.base import MessageRepository, SessionRepository, ToolCallLogRepository
from app.schemas.chat import ChatStreamRequest
from app.schemas.domain import IntentType, MessageRecord, MessageRole, SessionRecord, SessionStatus
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService


class _DefaultSettingsService:
    async def get_agent_preferences(self, user_id: str):
        _ = user_id
        return type(
            "PreferenceRecord",
            (),
            {"script_style": None, "custom_sensitive_terms": []},
        )()


class ChatService:
    # 聚合会话、消息、记忆、偏好与图运行时，负责统一聊天主链编排。
    def __init__(
        self,
        graph_runtime: GraphRuntime,
        session_repository: SessionRepository,
        message_repository: MessageRepository,
        memory_service: MemoryService,
        tool_log_repository: ToolCallLogRepository,
        settings_service: SettingsService | None = None,
    ):
        self.graph_runtime = graph_runtime
        self.session_repository = session_repository
        self.message_repository = message_repository
        self.memory_service = memory_service
        self.tool_log_repository = tool_log_repository
        self.settings_service = settings_service or _DefaultSettingsService()

    # 如果当前 session 不存在则创建，存在则保持原状态继续复用。
    async def ensure_session(self, session_id: str, user_id: str) -> SessionRecord:
        session = await self.session_repository.get(session_id)
        if session is None:
            session = SessionRecord(id=session_id, user_id=user_id, status=SessionStatus.active)
            await self.session_repository.save(session)
        return session

    # 持久化用户消息，保证后续复盘、记忆和追踪都能拿到原始输入。
    async def persist_user_message(self, session_id: str, content: str) -> MessageRecord:
        return await self.message_repository.create(
            MessageRecord(
                session_id=session_id,
                role=MessageRole.user,
                content=content,
            )
        )

    # 持久化 assistant 输出，并把 agent 相关元数据写入消息记录。
    async def persist_assistant_message(
        self,
        session_id: str,
        content: str,
        intent: str,
        metadata: dict,
    ) -> MessageRecord:
        return await self.message_repository.create(
            MessageRecord(
                session_id=session_id,
                role=MessageRole.assistant,
                content=content,
                intent=IntentType(intent),
                agent_name=metadata.get("agent_name"),
                metadata=metadata,
            )
        )

    # 统一构造图运行状态，把记忆、偏好和实时快照在进入 LangGraph 前补齐。
    async def _build_state(
        self,
        request: ChatStreamRequest,
        *,
        user_id: str,
        user_role: str | None,
        trace_id: str,
    ) -> dict:
        memory_snapshot = await self.memory_service.get_memory_snapshot(request.session_id)
        preferences = await self.settings_service.get_agent_preferences(user_id)

        resolved_script_style = request.script_style or preferences.script_style
        custom_sensitive_terms = preferences.custom_sensitive_terms

        return {
            "trace_id": trace_id,
            "session_id": request.session_id,
            "user_id": user_id,
            "user_role": user_role,
            "user_input": request.user_input,
            "live_stage": request.live_stage.value,
            "current_product_id": request.current_product_id,
            "short_term_memory": memory_snapshot["turns"],
            "hot_keywords": request.hot_keywords or memory_snapshot["hot_keywords"],
            "script_style": resolved_script_style,
            "custom_sensitive_terms": custom_sensitive_terms,
            "memory_status": memory_snapshot["status"],
            "live_offer_snapshot": request.live_offer_snapshot,
        }

    # 从图运行结果中抽取需要落库和前端消费的标准 metadata。
    def _build_message_metadata(self, result: dict) -> dict:
        metadata = {
            "agent_name": result.get("agent_name"),
            "guardrail_pass": result.get("guardrail_pass"),
            "guardrail_reason": result.get("guardrail_reason"),
            "guardrail_action": result.get("guardrail_action"),
            "guardrail_violations": result.get("guardrail_violations", []),
            "route_reason": result.get("route_reason"),
            "route_fallback_reason": result.get("route_fallback_reason"),
            "route_low_confidence": result.get("route_low_confidence"),
            "knowledge_scope": result.get("knowledge_scope"),
            "rewritten_query": result.get("rewritten_query"),
            "qa_confidence": result.get("qa_confidence"),
            "references": result.get("references", []),
            "unresolved": result.get("unresolved", False),
            "memory_status": result.get("memory_status"),
            "high_frequency_questions": result.get("high_frequency_questions", []),
        }
        if result.get("script_type"):
            metadata["script_type"] = result.get("script_type")
        if result.get("script_tone"):
            metadata["script_tone"] = result.get("script_tone")
        if result.get("script_reason"):
            metadata["script_reason"] = result.get("script_reason")
        if result.get("script_candidates") is not None:
            metadata["script_candidates"] = result.get("script_candidates", [])
        if result.get("analyst_report") is not None:
            metadata["analyst_report"] = result.get("analyst_report")
        if result.get("report_id"):
            metadata["report_id"] = result.get("report_id")
        return metadata

    # 处理在线聊天主链：会话补全、消息落库、状态构造、图调用、记忆刷新和最终落消息。
    async def run_chat(
        self,
        request: ChatStreamRequest,
        user_id: str,
        trace_id: str,
        user_role: str | None = None,
    ) -> tuple[dict, MessageRecord]:
        session = await self.ensure_session(request.session_id, user_id)
        session.current_product_id = request.current_product_id
        session.live_stage = request.live_stage
        await self.session_repository.save(session)

        await self.persist_user_message(request.session_id, request.user_input)

        with bind_observability(request.session_id, self.tool_log_repository):
            state = await self._build_state(
                request,
                user_id=user_id,
                user_role=user_role,
                trace_id=trace_id,
            )
            result = await self.graph_runtime.ainvoke(state)

        metadata = self._build_message_metadata(result)
        assistant = await self.persist_assistant_message(
            session_id=request.session_id,
            content=result["final_output"],
            intent=result["intent"],
            metadata=metadata,
        )

        # 异步外置前先至少把最新会话短期记忆刷新回 Redis，Redis 故障时自动降级为空记忆模式。
        await self.memory_service.refresh_short_term_memory(
            request.session_id,
            request.current_product_id,
            request.live_stage.value,
            request.hot_keywords,
        )
        return result, assistant
