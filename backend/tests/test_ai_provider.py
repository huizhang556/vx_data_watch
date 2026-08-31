from __future__ import annotations

import asyncio
from typing import Any

import httpx
from app import ai_service, main
from fastapi.testclient import TestClient


def _payload(model: str = "test-model", account_id: int = 1) -> dict[str, Any]:
    return {"account_id": account_id, "name": "测试 AI", "base_url": "https://ai.example.test/v1", "model": model, "protocol": "chat_completions", "api_key": "secret-test-key", "timeout_seconds": 30}


def test_provider_is_saved_only_after_successful_test(client: TestClient, auth: dict[str, str], account_id: int, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def success(**_kwargs: Any) -> str: return "连接成功"
    monkeypatch.setattr(main, "test_provider_values", success)
    saved = client.post("/api/ai/provider/test-and-save", headers=auth, json=_payload(account_id=account_id))
    assert saved.status_code == 200
    assert client.get(f"/api/ai/provider?account_id={account_id}").json()["model"] == "test-model"


def test_draft_models_and_test_do_not_change_saved_provider(client: TestClient, auth: dict[str, str], account_id: int, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def models(**_kwargs: Any) -> list[str]: return ["model-a", "model-b"]
    async def success(**_kwargs: Any) -> str: return "连接成功"
    monkeypatch.setattr(main, "list_provider_models", models)
    monkeypatch.setattr(main, "test_provider_values", success)
    draft = _payload("model-b", account_id)
    assert client.post("/api/ai/provider/models", headers=auth, json=draft).json() == {"models": ["model-a", "model-b"]}
    assert client.post("/api/ai/provider/test-draft", headers=auth, json=draft).status_code == 200
    async def failure(**_kwargs: Any) -> str: raise RuntimeError("provider rejected")
    monkeypatch.setattr(main, "test_provider_values", failure)
    assert client.post("/api/ai/provider/test-and-save", headers=auth, json=_payload("bad-model", account_id)).status_code == 502


def test_provider_model_cache_is_returned_and_used_by_quick_configs(
    client: TestClient, auth: dict[str, str], account_id: int, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    async def models(**_kwargs: Any) -> list[str]:
        return ["cached-a", "cached-b"]

    async def success(**_kwargs: Any) -> str:
        return "连接成功"

    monkeypatch.setattr(main, "list_provider_models", models)
    monkeypatch.setattr(main, "test_provider_values", success)
    provider = client.post(
        "/api/ai/provider/test-and-save",
        headers=auth,
        json={**_payload("cached-a", account_id), "models": ["cached-a", "cached-b"]},
    )
    assert provider.status_code == 200, provider.text
    provider_id = provider.json()["id"]

    listed = client.get(f"/api/ai/providers?account_id={account_id}")
    cached = next(row for row in listed.json() if row["id"] == provider_id)
    assert cached["models"] == ["cached-a", "cached-b"]

    quick = client.post(
        "/api/ai/quick-configs",
        headers=auth,
        json={"name": "缓存模型", "provider_id": provider_id, "model": "cached-b"},
    )
    assert quick.status_code == 201, quick.text
    invalid = client.post(
        "/api/ai/quick-configs",
        headers=auth,
        json={"name": "非法模型", "provider_id": provider_id, "model": "not-cached"},
    )
    assert invalid.status_code == 422


def test_native_provider_protocols(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    requests: list[httpx.Request] = []
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/messages"): return httpx.Response(200, json={"content": [{"type": "text", "text": "anthropic ok"}]})
        if "generateContent" in request.url.path: return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "gemini ok"}]}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "grok ok"}}]})
    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(ai_service.httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    async def run() -> list[str]:
        return [await ai_service._call_native_provider("https://anthropic.test", "claude", "anthropic", 10, "a-key", [{"role": "user", "content": "hi"}]), await ai_service._call_native_provider("https://gemini.test", "gemini", "gemini", 10, "g-key", [{"role": "user", "content": "hi"}]), await ai_service._call_native_provider("https://grok.test", "grok", "grok", 10, "x-key", [{"role": "user", "content": "hi"}])]
    assert asyncio.run(run()) == ["anthropic ok", "gemini ok", "grok ok"]
    assert requests[0].headers["x-api-key"] == "a-key"
    assert requests[1].url.params["key"] == "g-key"
    assert requests[2].headers["authorization"] == "Bearer x-key"


def test_ai_chat_end_to_end(client: TestClient, auth: dict[str, str], account_id: int, monkeypatch) -> None:
    async def success(**_kwargs: Any) -> str:
        return "连接成功"
    monkeypatch.setattr(main, "test_provider_values", success)
    provider = client.post("/api/ai/provider/test-and-save", headers=auth, json=_payload(account_id=account_id)).json()
    session = client.post("/api/ai-chat/sessions", headers=auth, json={"title": "自动化测试", "provider_id": provider["id"]})
    assert session.status_code == 201
    session_id = session.json()["id"]

    async def stream(*_args: Any, **_kwargs: Any):
        yield "模拟"
        yield "回复"
    monkeypatch.setattr(main, "stream_chat_provider", stream)
    response = client.post("/api/ai-chat/sessions/%s/messages" % session_id, headers=auth, json={"content": "你好", "attachments": [{"filename": "note.txt", "content_type": "text/plain", "data": "aGVsbG8="}]})
    assert response.status_code == 200
    messages = client.get(f"/api/ai-chat/sessions/{session_id}/messages", headers=auth).json()
    assert "done" in response.text, response.text
    assert [item["role"] for item in messages] == ["user", "assistant"], response.text
    attachment = messages[0]["attachments"][0]
    assert client.get(f"/api/ai-chat/attachments/{attachment['id']}", headers=auth).status_code == 200
    assert client.delete(f"/api/ai-chat/sessions/{session_id}", headers=auth).status_code == 204
    assert client.get(f"/api/ai-chat/sessions/{session_id}/messages", headers=auth).status_code == 404
