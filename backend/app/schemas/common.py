from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    status: str = "success"
    data: Any = None
    message: str = "Operation completed"


class ErrorResponse(BaseModel):
    status: str = "error"
    error: str
    message: str


class HealthResponse(BaseModel):
    status: str
    services: dict[str, str] = Field(default_factory=dict)
