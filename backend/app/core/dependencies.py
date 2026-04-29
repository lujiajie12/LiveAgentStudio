from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.security import decode_access_token
from app.infra.container import AppContainer
from app.schemas.auth import CurrentUser

bearer_scheme = HTTPBearer(auto_error=False)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    container: AppContainer = Depends(get_container),
) -> CurrentUser:
    if credentials is None:
        raise AppError("unauthorized", "Missing bearer token", 401)

    payload = decode_access_token(credentials.credentials, settings.JWT_SECRET)
    user = await container.user_repository.get_by_id(payload["sub"])
    if user is None:
        raise AppError("user_not_found", "User does not exist", 401)

    return CurrentUser.model_validate(user.model_dump())
