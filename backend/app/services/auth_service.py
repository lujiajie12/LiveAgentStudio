import hashlib

from app.core.config import settings
from app.core.security import create_access_token
from app.repositories.base import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.domain import UserRecord


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


class AuthService:
    def __init__(self, user_repository: UserRepository):
        self.user_repository = user_repository

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.user_repository.get_by_username(payload.username)
        password_hash = hash_password(payload.password)

        if user is None:
            user = UserRecord(
                username=payload.username,
                role=payload.role,
                password_hash=password_hash,
            )
            await self.user_repository.save(user)

        if user.password_hash != password_hash:
            from app.core.exceptions import AppError

            raise AppError("invalid_credentials", "Username or password is incorrect", 401)

        token = create_access_token(
            {"sub": user.id, "username": user.username, "role": user.role.value},
            secret=settings.JWT_SECRET,
            expires_in=settings.JWT_EXPIRE_SECONDS,
        )
        return TokenResponse(access_token=token, expires_in=settings.JWT_EXPIRE_SECONDS)
