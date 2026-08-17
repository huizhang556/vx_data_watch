from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_temp_dir = tempfile.TemporaryDirectory(prefix="vx-data-tests-", ignore_cleanup_errors=True)
os.environ["VX_DATA_DIR"] = _temp_dir.name
os.environ["VX_DATABASE_URL"] = f"sqlite:///{Path(_temp_dir.name) / 'test.db'}"
os.environ["VX_COOKIE_SECURE"] = "false"

_frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_frontend_index = _frontend_dist / "index.html"
_created_frontend_stub = not _frontend_index.exists()
if _created_frontend_stub:
    _frontend_dist.mkdir(parents=True, exist_ok=True)
    _frontend_index.write_text('<div id="root"></div>', encoding="utf-8")

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth(client: TestClient) -> dict[str, str]:
    response = client.post("/api/setup", json={"username": "admin", "password": "secure-pass-123"})
    assert response.status_code == 201, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture(scope="session")
def account_id(client: TestClient, auth: dict[str, str]) -> int:
    response = client.post(
        "/api/accounts",
        headers=auth,
        json={"name": "测试视频号", "description": "测试"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def pytest_sessionfinish() -> None:
    engine.dispose()
    _temp_dir.cleanup()
    if _created_frontend_stub:
        shutil.rmtree(_frontend_dist, ignore_errors=True)
