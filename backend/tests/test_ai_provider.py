from __future__ import annotations

from typing import Any

from app import main
from fastapi.testclient import TestClient


def _payload(model: str = "test-model", account_id: int = 1) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "name": "测试 AI",
        "base_url": "https://ai.example.test/v1",
        "model": model,
        "protocol": "chat_completions",
        "api_key": "secret-test-key",
        "timeout_seconds": 30,
    }


def test_provider_is_saved_only_after_successful_test(
    client: TestClient,
    auth: dict[str, str],
    account_id: int,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    async def success(**_kwargs: Any) -> str:
        return "连接成功"

    monkeypatch.setattr(main, "test_provider_values", success)
    saved = client.post("/api/ai/provider/test-and-save", headers=auth, json=_payload(account_id=account_id))
    assert saved.status_code == 200, saved.text
    assert saved.json()["result"] == "连接成功"
    assert client.get(f"/api/ai/provider?account_id={account_id}").json()["model"] == "test-model"


def test_draft_models_and_test_do_not_change_saved_provider(
    client: TestClient,
    auth: dict[str, str],
    account_id: int,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    async def models(**_kwargs: Any) -> list[str]:
        return ["model-a", "model-b"]

    async def success(**_kwargs: Any) -> str:
        return "连接成功"

    monkeypatch.setattr(main, "list_provider_models", models)
    monkeypatch.setattr(main, "test_provider_values", success)
    draft = _payload("model-b", account_id)
    listed = client.post("/api/ai/provider/models", headers=auth, json=draft)
    assert listed.status_code == 200, listed.text
    assert listed.json() == {"models": ["model-a", "model-b"]}

    tested = client.post("/api/ai/provider/test-draft", headers=auth, json=draft)
    assert tested.status_code == 200, tested.text
    assert tested.json()["result"] == "连接成功"
    assert client.get(f"/api/ai/provider?account_id={account_id}").json()["model"] == "test-model"

    async def failure(**_kwargs: Any) -> str:
        raise RuntimeError("连接被拒绝")

    monkeypatch.setattr(main, "test_provider_values", failure)
    rejected = client.post(
        "/api/ai/provider/test-and-save", headers=auth, json=_payload("bad-model", account_id)
    )
    assert rejected.status_code == 502
    assert client.get(f"/api/ai/provider?account_id={account_id}").json()["model"] == "test-model"
