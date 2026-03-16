import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict

from app.core.exceptions import AppError


def _urlsafe_encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _urlsafe_decode(payload: str) -> bytes:
    padding = "=" * ((4 - len(payload) % 4) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def create_access_token(data: Dict[str, Any], secret: str, expires_in: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = data.copy()
    payload["exp"] = int(time.time()) + expires_in

    header_b64 = _urlsafe_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _urlsafe_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    signature_b64 = _urlsafe_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_access_token(token: str, secret: str) -> Dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise AppError("invalid_token", "Malformed access token", 401) from exc

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    actual_signature = _urlsafe_decode(signature_b64)

    if not hmac.compare_digest(expected_signature, actual_signature):
        raise AppError("invalid_token", "Invalid access token signature", 401)

    payload = json.loads(_urlsafe_decode(payload_b64))
    if payload.get("exp", 0) < int(time.time()):
        raise AppError("expired_token", "Access token expired", 401)

    return payload
