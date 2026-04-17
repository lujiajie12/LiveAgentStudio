from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.observability import bind_observability
from app.graph.runtime import GraphRuntime
from app.repositories.base import MessageRepository, SessionRepository, ToolCallLogRepository
from app.schemas.chat import ChatStreamRequest
from app.schemas.domain import IntentType, MessageRecord, MessageRole, SessionRecord, SessionStatus
from app.services.memory_service import MemoryService
from app.services.settings_service import SettingsService

if TYPE_CHECKING:
    from app.memory.qa_agent_memory_hook import QAMemoryHook


class _DefaultSettingsService:
    async def get_agent_preferences(self, user_id: str):
        _ = user_id
        return type(
            "PreferenceRecord",
            (),
            {"script_style": None, "custom_sensitive_terms": []},
        )()


class ChatService:
    # ChatService 是在线聊天主链的总编排层：
    # 负责会话补全、消息落库、状态构造、图运行、记忆刷新，以及最终回复的持久化。
    def __init__(
        self,
        graph_runtime: GraphRuntime,
        session_repository: SessionRepository,
        message_repository: MessageRepository,
        memory_service: MemoryService,
        tool_log_repository: ToolCallLogRepository,
        settings_service: SettingsService | None = None,
        qa_memory_hook: "QAMemoryHook | None" = None,
    ):
        self.graph_runtime = graph_runtime
        self.session_repository = session_repository
        self.message_repository = message_repository
        self.memory_service = memory_service
        self.tool_log_repository = tool_log_repository
        self.settings_service = settings_service or _DefaultSettingsService()
        self.qa_memory_hook = qa_memory_hook

    # 确保会话存在。
    # 如果 session 已存在，则直接复用；如果不存在，则创建一条 active 会话记录，
    # 这样后面的消息、记忆、工具日志都能挂在同一个 session 下。
    async def ensure_session(self, session_id: str, user_id: str) -> SessionRecord:
        session = await self.session_repository.get(session_id)
        if session is None:
            session = SessionRecord(id=session_id, user_id=user_id, status=SessionStatus.active)
            await self.session_repository.save(session)
        return session

    # 持久化用户消息。
    # 这里先存原始输入，避免后续图运行失败时连“用户到底问了什么”都无从追踪。
    async def persist_user_message(self, session_id: str, content: str) -> MessageRecord:
        return await self.message_repository.create(
            MessageRecord(
                session_id=session_id,
                role=MessageRole.user,
                content=content,
            )
        )

    # 持久化 assistant 消息。
    # 除了回复正文，这里还会把 agent、路由、工具、引用、记忆命中等 metadata 一并存下，
    # 方便前端展示和后端排障。
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

    # 统一构造图运行状态。
    # 这里会把请求参数、短期记忆、用户偏好、敏感词配置、直播快照等上下文整合进 state，
    # 后面的 planner / executor / qa / guardrail 都基于这份 state 工作。
    async def _build_state(
        self,
        request: ChatStreamRequest,
        *,
        user_id: str,
        user_role: str | None,
        trace_id: str,
    ) -> dict:
        # 先拿短期记忆快照，里面包含最近几轮对话与会话热词。
        memory_snapshot = await self.memory_service.get_memory_snapshot(request.session_id)
        # 再拿用户级偏好，例如脚本风格、自定义敏感词。
        preferences = await self.settings_service.get_agent_preferences(user_id)

        # 请求级参数优先于偏好配置；这次请求显式指定了 script_style 就优先采用。
        resolved_script_style = request.script_style or preferences.script_style
        custom_sensitive_terms = preferences.custom_sensitive_terms

        # 返回统一 state。
        # 注意：这里是“图运行的上下文输入”，不是最终要落库的消息 metadata。
        return {
            "trace_id": trace_id,
            "session_id": request.session_id,
            "user_id": user_id,
            "user_role": user_role,
            "app_id": getattr(settings, "QA_MEMORY_APP_ID", "liveagent-studio"),
            "run_id": trace_id,
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

    # 从图运行结果中抽取标准 metadata。
    # 这份 metadata 会跟 assistant 消息一起落库，也会被前端用于展示工具、引用和路由信息。
    def _build_message_metadata(self, result: dict) -> dict:
        metadata = {
            "agent_name": result.get("agent_name"),
            "guardrail_pass": result.get("guardrail_pass"),
            "guardrail_reason": result.get("guardrail_reason"),
            "guardrail_action": result.get("guardrail_action"),
            "guardrail_violations": result.get("guardrail_violations", []),
            "route_reason": result.get("route_reason"),
            "route_target": result.get("route_target"),
            "requires_retrieval": result.get("requires_retrieval"),
            "route_fallback_reason": result.get("route_fallback_reason"),
            "route_low_confidence": result.get("route_low_confidence"),
            "knowledge_scope": result.get("knowledge_scope"),
            "tool_intent": result.get("tool_intent"),
            "memory_recall_request": result.get("memory_recall_request"),
            "planner_mode": result.get("planner_mode"),
            "planner_action": result.get("planner_action"),
            "planner_step_count": result.get("planner_step_count"),
            "planner_trace": result.get("planner_trace", []),
            "executor_observations": result.get("executor_observations", []),
            "rewritten_query": result.get("rewritten_query"),
            "query_budget": result.get("query_budget"),
            "qa_confidence": result.get("qa_confidence"),
            "references": result.get("references", []),
            "unresolved": result.get("unresolved", False),
            "memory_status": result.get("memory_status"),
            "high_frequency_questions": result.get("high_frequency_questions", []),
            "tools_used": result.get("tools_used", []),
            "tool_outputs": result.get("tool_outputs", {}),
            "long_term_memories": result.get("long_term_memories", []),
            "long_term_memory_hits": result.get("long_term_memory_hits", 0),
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

    # 处理在线聊天主链：
    # 1. 补全/更新会话
    # 2. 先落用户消息
    # 3. 构造 state 并调用 LangGraph 主图
    # 4. 抽取 metadata 并落 assistant 消息
    # 5. 刷新短期记忆，并在 QA 场景下沉淀长期记忆
    async def run_chat(
        self,
        request: ChatStreamRequest,
        user_id: str,
        trace_id: str,
        user_role: str | None = None,
    ) -> tuple[dict, MessageRecord]:
        # 先确保会话存在，再把本轮直播态信息写回 session。
        # 这样后续服务只拿 session，也能知道当前商品和直播阶段。
        session = await self.ensure_session(request.session_id, user_id)
        session.current_product_id = request.current_product_id
        session.live_stage = request.live_stage
        await self.session_repository.save(session)

        # 用户消息必须先入库，避免中途失败后无法复盘原始问题。
        await self.persist_user_message(request.session_id, request.user_input)

        # 绑定本轮会话级可观测上下文。
        # 从这里开始，图中所有节点和工具日志都会自动关联到当前 session。
        with bind_observability(request.session_id, self.tool_log_repository):
            # 组装图运行需要的完整上下文。
            state = await self._build_state(
                request,
                user_id=user_id,
                user_role=user_role,
                trace_id=trace_id,
            )
            # 正式进入 LangGraph 主图，得到本轮编排后的完整结果。
            result = await self.graph_runtime.ainvoke(state)

        # 把运行结果压缩成更适合落库和前端展示的 metadata。
        metadata = self._build_message_metadata(result)
        # 最终 assistant 消息和 metadata 一起持久化。
        assistant = await self.persist_assistant_message(
            session_id=request.session_id,
            content=result["final_output"],
            intent=result["intent"],
            metadata=metadata,
        )

        # 至少先把最新短期记忆刷新回 Redis。
        # 即便长期记忆链路出问题，下一轮对话也仍然能读到最近上下文。
        await self.memory_service.refresh_short_term_memory(
            request.session_id,
            request.current_product_id,
            request.live_stage.value,
            request.hot_keywords,
        )
        if self.qa_memory_hook is not None and result.get("agent_name") == "qa":
            try:
                # 只有 QA 场景写长期记忆。
                # direct/script/analyst 这类结果很多是流程性或一次性内容，不适合直接沉淀。
                await self.qa_memory_hook.remember_qa_interaction(
                    user_input=request.user_input,
                    assistant_output=result["final_output"],
                    user_id=user_id,
                    run_id=trace_id,
                    current_product_id=request.current_product_id,
                    metadata=metadata,
                )
            except Exception:
                # 长期记忆写入失败不影响主链返回，避免把增强能力做成单点故障。
                pass
        # 同时返回运行结果和已落库的 assistant 消息。
        # 上层既可以拿 result 做调试，也可以拿 assistant 做展示。
        return result, assistant
