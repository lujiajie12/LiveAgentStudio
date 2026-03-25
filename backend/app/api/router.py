from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.memory import router as memory_router
from app.api.ops import router as ops_router
from app.api.rag import router as rag_router
from app.api.reports import router as reports_router
from app.api.settings import router as settings_router
from app.api.system import router as system_router
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(documents_router)
router.include_router(system_router)
router.include_router(reports_router)
router.include_router(memory_router)
router.include_router(settings_router)
router.include_router(ops_router)
router.include_router(rag_router)


@router.get("/", response_model=ApiResponse, tags=["root"])
async def root():
    return ApiResponse(data={"message": "LiveAgentStudio API v1"})
