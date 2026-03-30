from fastapi import APIRouter, Depends

from app.core.dependencies import get_container, get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=ApiResponse)
async def system_health(
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    return ApiResponse(data=await container.system_service.get_health())


@router.get("/metrics", response_model=ApiResponse)
async def system_metrics(
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    return ApiResponse(data=await container.system_service.get_metrics())
