from app.repositories.base import KnowledgeRepository
from app.schemas.document import DocumentCreateRequest
from app.schemas.domain import KnowledgeDocumentRecord


class KnowledgeService:
    def __init__(self, knowledge_repository: KnowledgeRepository):
        self.knowledge_repository = knowledge_repository

    async def create_document(
        self, payload: DocumentCreateRequest
    ) -> KnowledgeDocumentRecord:
        document = KnowledgeDocumentRecord(
            title=payload.title,
            source_type=payload.source_type,
            content=payload.content,
            product_id=payload.product_id,
            metadata=payload.metadata,
        )
        return await self.knowledge_repository.create(document)

    async def search(
        self, query: str, product_id: str | None = None
    ) -> list[KnowledgeDocumentRecord]:
        documents = await self.knowledge_repository.list_active()
        lowered = query.lower()

        filtered = [
            doc
            for doc in documents
            if (product_id is None or doc.product_id in (None, product_id))
            and (
                lowered in doc.title.lower()
                or lowered in doc.content.lower()
                or not lowered.strip()
            )
        ]
        return filtered[:3]
