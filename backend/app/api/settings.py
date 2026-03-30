from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends

from app.core.dependencies import get_container, get_current_user
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/settings", tags=["settings"])


class AgentPreferenceUpdateRequest(BaseModel):
    script_style: str | None = None
    custom_sensitive_terms: list[str] = Field(default_factory=list)


@router.get("/agent-preferences", response_model=ApiResponse)
async def get_agent_preferences(
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    record = await container.settings_service.get_agent_preferences(current_user.id)
    return ApiResponse(data=record.model_dump(mode="json"))


@router.put("/agent-preferences", response_model=ApiResponse)
async def update_agent_preferences(
    payload: AgentPreferenceUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    record = await container.settings_service.update_agent_preferences(
        current_user.id,
        script_style=payload.script_style,
        custom_sensitive_terms=payload.custom_sensitive_terms,
    )
    return ApiResponse(data=record.model_dump(mode="json"))
