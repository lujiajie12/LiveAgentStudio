from fastapi import APIRouter

from app.schemas.common import HealthResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def system_health():
    return HealthResponse(
        status="ok",
        services={
            "api": "ok",
            "graph": "ok",
            "memory": "degraded",
            "vector_store": "degraded",
        },
    )
