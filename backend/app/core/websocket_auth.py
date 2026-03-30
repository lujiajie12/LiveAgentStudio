from fastapi import WebSocket

from app.core.config import settings
from app.core.security import decode_access_token
from app.infra.container import AppContainer
from app.schemas.auth import CurrentUser


async def authenticate_websocket(websocket: WebSocket, container: AppContainer) -> CurrentUser | None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return None

    try:
        payload = decode_access_token(token, settings.JWT_SECRET)
    except Exception:
        await websocket.close(code=4401, reason="Invalid token")
        return None

    user = await container.user_repository.get_by_id(payload["sub"])
    if user is None:
        await websocket.close(code=4401, reason="User not found")
        return None

    return CurrentUser.model_validate(user.model_dump())
