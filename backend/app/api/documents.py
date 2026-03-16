from fastapi import APIRouter, Depends

from app.core.dependencies import get_container, get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse
from app.schemas.document import DocumentCreateRequest, DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=ApiResponse)
async def create_document(
    payload: DocumentCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    document = await container.knowledge_service.create_document(payload)
    response = DocumentResponse(
        id=document.id,
        title=document.title,
        source_type=document.source_type,
        product_id=document.product_id,
        metadata=document.metadata,
    )
    return ApiResponse(data=response.model_dump(mode="json"), message="Document created")
