from fastapi import APIRouter, Depends

from app.core.dependencies import get_container, get_current_user
from app.core.exceptions import AppError
from app.schemas.auth import CurrentUser
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=ApiResponse)
async def list_reports(
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    reports = await container.report_repository.list_recent(limit=50)
    return ApiResponse(data=[item.model_dump(mode="json") for item in reports])


@router.get("/{report_id}", response_model=ApiResponse)
async def get_report(
    report_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    container=Depends(get_container),
):
    _ = current_user
    report = await container.report_repository.get(report_id)
    if report is None:
        raise AppError("report_not_found", "Report does not exist", 404)
    return ApiResponse(data=report.model_dump(mode="json"))
