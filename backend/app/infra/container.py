from dataclasses import dataclass

from app.agents.router import RouterAgent
from app.core.config import settings
from app.graph.runtime import GraphRuntime
from app.repositories.in_memory import (
    InMemoryKnowledgeRepository,
    InMemoryMessageRepository,
    InMemoryReportRepository,
    InMemorySessionRepository,
    InMemoryToolCallLogRepository,
    InMemoryUserRepository,
)
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.guardrail_service import GuardrailService
from app.services.knowledge_service import KnowledgeService
from app.services.llm_gateway import OpenAILLMGateway
from app.services.memory_service import MemoryService
from app.services.streaming_service import StreamingService


@dataclass
class AppContainer:
    user_repository: InMemoryUserRepository
    session_repository: InMemorySessionRepository
    message_repository: InMemoryMessageRepository
    knowledge_repository: InMemoryKnowledgeRepository
    tool_log_repository: InMemoryToolCallLogRepository
    report_repository: InMemoryReportRepository
    auth_service: AuthService
    memory_service: MemoryService
    knowledge_service: KnowledgeService
    guardrail_service: GuardrailService
    streaming_service: StreamingService
    graph_runtime: GraphRuntime
    chat_service: ChatService


def build_container() -> AppContainer:
    user_repository = InMemoryUserRepository()
    session_repository = InMemorySessionRepository()
    message_repository = InMemoryMessageRepository()
    knowledge_repository = InMemoryKnowledgeRepository()
    tool_log_repository = InMemoryToolCallLogRepository()
    report_repository = InMemoryReportRepository()

    auth_service = AuthService(user_repository)
    memory_service = MemoryService(message_repository, settings.MEMORY_WINDOW_SIZE)
    knowledge_service = KnowledgeService(knowledge_repository)
    guardrail_service = GuardrailService(settings.SENSITIVE_TERMS)
    streaming_service = StreamingService(
        chunk_size=settings.CHAT_TOKEN_CHUNK_SIZE,
        event_delay_ms=settings.SSE_EVENT_DELAY_MS,
    )
    llm_gateway = OpenAILLMGateway()
    router_agent = RouterAgent(llm_gateway)
    graph_runtime = GraphRuntime(router_agent, guardrail_service)
    chat_service = ChatService(
        graph_runtime=graph_runtime,
        session_repository=session_repository,
        message_repository=message_repository,
        memory_service=memory_service,
        tool_log_repository=tool_log_repository,
    )

    return AppContainer(
        user_repository=user_repository,
        session_repository=session_repository,
        message_repository=message_repository,
        knowledge_repository=knowledge_repository,
        tool_log_repository=tool_log_repository,
        report_repository=report_repository,
        auth_service=auth_service,
        memory_service=memory_service,
        knowledge_service=knowledge_service,
        guardrail_service=guardrail_service,
        streaming_service=streaming_service,
        graph_runtime=graph_runtime,
        chat_service=chat_service,
    )
