from pydantic import BaseModel, Field

from app.schemas.domain import UserRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    role: UserRole = UserRole.operator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUser(BaseModel):
    id: str
    username: str
    role: UserRole
    tenant_id: str | None = None
