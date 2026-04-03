from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.analyst_agent import AnalystAgent
from app.agents.direct_reply_agent import DirectReplyAgent
from app.agents.qa_agent import ChatOpenAIJsonClient, QAAgent
from app.agents.router import RouterAgent
from app.agents.script_agent import ScriptAgent
from app.core.config import settings
from app.graph.runtime import GraphRuntime
from app.memory.memory_policy import MemoryPolicy
from app.memory.memory_service import LongTermMemoryService
from app.memory.qa_agent_memory_hook import QAMemoryHook
from app.infra.database import build_engine, build_session_factory, init_db
from app.rag.hybrid_retrieval_pipeline import HybridRetrievalPipeline
from app.rag.indexes import BM25Index, DashScopeReranker, LocalReranker, MockReranker, VectorIndex
from app.repositories.base import (
    AgentPreferenceRepository,
    HighFrequencyQuestionRepository,
    KnowledgeRepository,
    LiveBarrageEventRepository,
    MessageRepository,
    RagOfflineJobRepository,
    ReportRepository,
    SessionRepository,
    TeleprompterItemRepository,
    ToolCallLogRepository,
    UserRepository,
)
from app.repositories.sqlalchemy import (
    SQLAlchemyAgentPreferenceRepository,
    SQLAlchemyHighFrequencyQuestionRepository,
    SQLAlchemyKnowledgeRepository,
    SQLAlchemyLiveBarrageEventRepository,
    SQLAlchemyMessageRepository,
    SQLAlchemyRagOfflineJobRepository,
    SQLAlchemyReportRepository,
    SQLAlchemySessionRepository,
    SQLAlchemyTeleprompterItemRepository,
    SQLAlchemyToolCallLogRepository,
    SQLAlchemyUserRepository,
)
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.guardrail_service import GuardrailService
from app.services.knowledge_service import KnowledgeService
from app.services.llm_gateway import OpenAILLMGateway
from app.services.live_barrage_service import LiveBarrageService
from app.services.memory_service import MemoryService, build_redis_client
from app.services.ops_service import OpsService
from app.services.rag_ops_service import RagOpsService
from app.services.settings_service import SettingsService
from app.services.streaming_service import StreamingService
from app.services.system_service import SystemService
from app.services.teleprompter_service import TeleprompterService


@dataclass
class AppContainer:
    db_engine: Any
    session_factory: Any
    redis_client: Any
    user_repository: UserRepository
    session_repository: SessionRepository
    message_repository: MessageRepository
    knowledge_repository: KnowledgeRepository
    live_barrage_repository: LiveBarrageEventRepository
    tool_log_repository: ToolCallLogRepository
    report_repository: ReportRepository
    high_frequency_repository: HighFrequencyQuestionRepository
    agent_preference_repository: AgentPreferenceRepository
    teleprompter_repository: TeleprompterItemRepository
    rag_job_repository: RagOfflineJobRepository
    auth_service: AuthService
    memory_service: MemoryService
    qa_long_term_memory_service: LongTermMemoryService
    settings_service: SettingsService
    knowledge_service: KnowledgeService
    guardrail_service: GuardrailService
    streaming_service: StreamingService
    system_service: SystemService
    live_barrage_service: LiveBarrageService
    teleprompter_service: TeleprompterService
    ops_service: OpsService
    rag_ops_service: RagOpsService
    graph_runtime: GraphRuntime
    chat_service: ChatService
    retrieval_pipeline: HybridRetrievalPipeline
    bm25_index: BM25Index
    vector_index: VectorIndex


def build_container() -> AppContainer:
    # 初始化真实数据库与 session factory，本轮不再走默认内存仓库。
    db_engine = build_engine(settings.DATABASE_URL)
    init_db(db_engine)
    session_factory = build_session_factory(db_engine)
    redis_client = build_redis_client(settings.REDIS_URL)

    user_repository = SQLAlchemyUserRepository(session_factory)
    session_repository = SQLAlchemySessionRepository(session_factory)
    message_repository = SQLAlchemyMessageRepository(session_factory)
    knowledge_repository = SQLAlchemyKnowledgeRepository(session_factory)
    live_barrage_repository = SQLAlchemyLiveBarrageEventRepository(session_factory)
    tool_log_repository = SQLAlchemyToolCallLogRepository(session_factory)
    report_repository = SQLAlchemyReportRepository(session_factory)
    high_frequency_repository = SQLAlchemyHighFrequencyQuestionRepository(session_factory)
    agent_preference_repository = SQLAlchemyAgentPreferenceRepository(session_factory)
    teleprompter_repository = SQLAlchemyTeleprompterItemRepository(session_factory)
    rag_job_repository = SQLAlchemyRagOfflineJobRepository(session_factory)

    auth_service = AuthService(user_repository)
    memory_service = MemoryService(
        message_repository=message_repository,
        window_size=settings.MEMORY_WINDOW_SIZE,
        redis_client=redis_client,
        ttl_seconds=settings.MEMORY_TTL_SECONDS,
        hot_keywords_ttl_seconds=settings.HOT_KEYWORDS_TTL_SECONDS,
    )
    qa_long_term_memory_service = LongTermMemoryService.from_mem0_config(
        api_key=settings.MEM0_API_KEY,
        base_url=settings.MEM0_BASE_URL,
        org_id=settings.MEM0_ORG_ID,
        project_id=settings.MEM0_PROJECT_ID,
        enabled=settings.QA_MEMORY_ENABLED,
        similarity_threshold=settings.QA_MEMORY_THRESHOLD,
    )
    settings_service = SettingsService(agent_preference_repository)
    knowledge_service = KnowledgeService()
    guardrail_service = GuardrailService(settings.SENSITIVE_TERMS)
    streaming_service = StreamingService(
        chunk_size=settings.CHAT_TOKEN_CHUNK_SIZE,
        event_delay_ms=settings.SSE_EVENT_DELAY_MS,
    )

    llm_gateway = OpenAILLMGateway()
    bm25_index = BM25Index(host=settings.ES_HOST, port=settings.ES_PORT)
    vector_index = VectorIndex(host=settings.MILVUS_HOST, port=settings.MILVUS_PORT)
    # 优先使用本地 reranker，其次 DashScope，最后 Mock
    reranker = MockReranker()
    if settings.USE_LOCAL_RERANKER:
        reranker = LocalReranker(model=settings.RERANKER_MODEL, device=settings.RERANKER_DEVICE)
    else:
        dashscope_key = settings.DASHSCOPE_API_KEY or settings.LLM_API_KEY or ""
        if dashscope_key:
            reranker = DashScopeReranker(model="gte-rerank", api_key=dashscope_key)

    retrieval_pipeline = HybridRetrievalPipeline(
        llm_client=llm_gateway,
        bm25_index=bm25_index,
        vector_index=vector_index,
        reranker_client=reranker,
        n_expansions=2,
    )

    router_agent = RouterAgent(llm_gateway)
    qa_agent = QAAgent(
        retrieval_pipeline=retrieval_pipeline,
        llm_client=ChatOpenAIJsonClient(label="qa"),
    )
    qa_agent.bind_high_frequency_repository(high_frequency_repository)
    qa_agent.bind_memory_hook(
        QAMemoryHook(
            memory_service=qa_long_term_memory_service,
            policy=MemoryPolicy(),
            agent_id=settings.QA_MEMORY_AGENT_ID,
            app_id=settings.QA_MEMORY_APP_ID,
            top_k=settings.QA_MEMORY_TOP_K,
            threshold=settings.QA_MEMORY_THRESHOLD,
        )
    )
    direct_agent = DirectReplyAgent(
        llm_client=ChatOpenAIJsonClient(label="direct_reply"),
    )
    script_agent = ScriptAgent(
        retrieval_pipeline=retrieval_pipeline,
        llm_client=ChatOpenAIJsonClient(label="script"),
    )
    analyst_agent = AnalystAgent(
        message_repository=message_repository,
        session_repository=session_repository,
        report_repository=report_repository,
        high_frequency_repository=high_frequency_repository,
        llm_client=ChatOpenAIJsonClient(label="analyst"),
    )

    graph_runtime = GraphRuntime(
        router_agent=router_agent,
        guardrail_service=guardrail_service,
        retrieval_pipeline=retrieval_pipeline,
        qa_agent=qa_agent,
        direct_agent=direct_agent,
        script_agent=script_agent,
        analyst_agent=analyst_agent,
    )
    chat_service = ChatService(
        graph_runtime=graph_runtime,
        session_repository=session_repository,
        message_repository=message_repository,
        memory_service=memory_service,
        tool_log_repository=tool_log_repository,
        settings_service=settings_service,
        qa_memory_hook=qa_agent.memory_hook,
    )
    system_service = SystemService(
        db_engine=db_engine,
        memory_service=memory_service,
        bm25_index=bm25_index,
        vector_index=vector_index,
        tool_log_repository=tool_log_repository,
    )
    live_barrage_service = LiveBarrageService(
        redis_client=redis_client,
        barrage_repository=live_barrage_repository,
        session_repository=session_repository,
        tool_log_repository=tool_log_repository,
    )
    teleprompter_service = TeleprompterService(
        redis_client=redis_client,
        teleprompter_repository=teleprompter_repository,
        tool_log_repository=tool_log_repository,
    )
    ops_service = OpsService(
        tool_log_repository=tool_log_repository,
        memory_service=memory_service,
        message_repository=message_repository,
        session_repository=session_repository,
        barrage_repository=live_barrage_repository,
    )
    rag_ops_service = RagOpsService(
        retrieval_pipeline=retrieval_pipeline,
        qa_agent=qa_agent,
        bm25_index=bm25_index,
        vector_index=vector_index,
        rag_job_repository=rag_job_repository,
    )

    return AppContainer(
        db_engine=db_engine,
        session_factory=session_factory,
        redis_client=redis_client,
        user_repository=user_repository,
        session_repository=session_repository,
        message_repository=message_repository,
        knowledge_repository=knowledge_repository,
        live_barrage_repository=live_barrage_repository,
        tool_log_repository=tool_log_repository,
        report_repository=report_repository,
        high_frequency_repository=high_frequency_repository,
        agent_preference_repository=agent_preference_repository,
        teleprompter_repository=teleprompter_repository,
        rag_job_repository=rag_job_repository,
        auth_service=auth_service,
        memory_service=memory_service,
        qa_long_term_memory_service=qa_long_term_memory_service,
        settings_service=settings_service,
        knowledge_service=knowledge_service,
        guardrail_service=guardrail_service,
        streaming_service=streaming_service,
        system_service=system_service,
        live_barrage_service=live_barrage_service,
        teleprompter_service=teleprompter_service,
        ops_service=ops_service,
        rag_ops_service=rag_ops_service,
        graph_runtime=graph_runtime,
        chat_service=chat_service,
        retrieval_pipeline=retrieval_pipeline,
        bm25_index=bm25_index,
        vector_index=vector_index,
    )
