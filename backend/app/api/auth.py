from fastapi import APIRouter, Depends

from app.core.dependencies import get_container, get_current_user
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from app.schemas.common import ApiResponse

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=ApiResponse)
async def login(payload: LoginRequest, container=Depends(get_container)):
    token = await container.auth_service.login(payload)
    return ApiResponse(data=token.model_dump(), message="Login successful")


@router.get("/me", response_model=ApiResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return ApiResponse(data=current_user.model_dump())
