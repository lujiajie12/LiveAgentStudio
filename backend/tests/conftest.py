import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


test_db_path = Path("backend") / "test_liveagent.db"
if test_db_path.exists():
    test_db_path.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path.as_posix()}"
os.environ["REDIS_URL"] = "memory://local"
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "username": "tester",
            "password": "demo",
            "role": "operator",
        },
    )
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
