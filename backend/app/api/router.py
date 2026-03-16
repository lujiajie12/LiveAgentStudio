from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["root"])


@router.get("/")
async def root():
    return {"message": "LiveAgentStudio API v1"}
