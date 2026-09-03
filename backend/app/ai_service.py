from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from .models import AIProviderConfig
from .security import decrypt_secret

SYSTEM_PROMPT = """你是视频号数据分析顾问。只依据用户提供的结构化数据分析，不得编造完播率、受众画像、流量来源或其他缺失指标。
输出必须包含：数据观察、异常与趋势、高贡献视频、可能原因、优化建议、验证方法、数据限制。
把推测明确标为推测，建议要具体且可验证。使用简体中文 Markdown；可使用标题、列表、表格和强调，不要输出 HTML 或脚本。"""


def _base_candidates(base_url: str) -> list[str]:
    """Try the common OpenAI-compatible root and /v1 forms without UI suffixes."""
    base = base_url.strip().rstrip("/")
    path = base.split("?", 1)[0].rstrip("/").lower()
    if path.endswith(("/v1", "/v2")):
        return [base]
    return [f"{base}/v1", base]


def _endpoint(base_url: str, suffix: str) -> str:
    return base_url.rstrip("/") + suffix


def build_prompt(snapshot: dict[str, Any]) -> str:
    return "请分析以下视频号数据：\n" + json.dumps(snapshot, ensure_ascii=False)


def _extract_responses_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    texts: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(content["text"])
    return "\n".join(texts)


async def _call_provider(
    *,
    base_url: str,
    model: str,
    protocol: str,
    timeout_seconds: int,
    api_key: str,
    snapshot: dict[str, Any],
) -> str:
    if protocol in {"anthropic", "gemini", "grok"}:
        return await _call_native_provider(base_url, model, protocol, timeout_seconds, api_key, [{"role": "user", "content": build_prompt(snapshot)}])
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    user_content = build_prompt(snapshot)
    if protocol == "responses":
        body = {
            "model": model,
            "instructions": SYSTEM_PROMPT,
            "input": user_content,
        }
    else:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        response = None
        for candidate in _base_candidates(base_url):
            response = await client.post(_endpoint(candidate, f"/{'responses' if protocol == 'responses' else 'chat/completions'}"), headers=headers, json=body)
            if response.status_code != 404:
                break
        assert response is not None
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text[:500]
        raise RuntimeError(f"AI 接口返回 {response.status_code}: {detail}") from exc
    payload = response.json()
    if protocol == "responses":
        text = _extract_responses_text(payload)
    else:
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("AI 接口响应缺少 choices[0].message.content") from exc
    if not text:
        raise RuntimeError("AI 接口返回了空内容")
    return str(text)


def _content_items(content: Any) -> list[dict[str, Any]]:
    return content if isinstance(content, list) else ([{"type": "text", "text": str(content)}] if content else [])


def _responses_request(messages: list[dict[str, Any]]) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert Chat Completions messages to the Responses API input schema."""
    instructions: str | None = None
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        if role == "system":
            instructions = str(message.get("content") or "")
            continue
        content = message.get("content")
        if isinstance(content, str):
            items = [{"type": "input_text", "text": content}]
        else:
            items = []
            for item in _content_items(content):
                item_type = item.get("type")
                if item_type == "text":
                    items.append({"type": "input_text", "text": str(item.get("text", ""))})
                elif item_type == "image_url":
                    image = item.get("image_url", {})
                    url = image.get("url", "") if isinstance(image, dict) else image
                    if url:
                        items.append({"type": "input_image", "image_url": str(url)})
            if not items:
                items = [{"type": "input_text", "text": ""}]
        converted.append({"role": role if role in {"user", "assistant", "developer"} else "user", "content": items})
    return instructions, converted


def _anthropic_content(content: Any) -> str | list[dict[str, Any]]:
    items = _content_items(content)
    if not any(item.get("type") == "image_url" for item in items):
        return str(content or "") if not isinstance(content, list) else items
    converted: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") == "image_url":
            url = str(item.get("image_url", {}).get("url", ""))
            header, _, data = url.partition(",")
            media_type = header.removeprefix("data:").removesuffix(";base64") or "image/png"
            converted.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
        elif item.get("type") == "text":
            converted.append({"type": "text", "text": str(item.get("text", ""))})
    return converted


def _gemini_parts(content: Any) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for item in _content_items(content):
        if item.get("type") == "image_url":
            url = str(item.get("image_url", {}).get("url", ""))
            header, _, data = url.partition(",")
            parts.append({"inline_data": {"mime_type": header.removeprefix("data:").removesuffix(";base64") or "image/png", "data": data}})
        elif item.get("type") == "text":
            parts.append({"text": str(item.get("text", ""))})
    return parts or [{"text": ""}]


async def _call_native_provider(base_url: str, model: str, protocol: str, timeout_seconds: int, api_key: str, messages: list[dict[str, Any]]) -> str:
    """Call vendor-native APIs while keeping the configured base URL as the root."""
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        if protocol == "anthropic":
            system = next((str(item["content"]) for item in messages if item.get("role") == "system"), None)
            body = {"model": model, "max_tokens": 4096, "messages": [{"role": item["role"], "content": _anthropic_content(item.get("content"))} for item in messages if item.get("role") != "system"]}
            if system:
                body["system"] = system
            response = await client.post(_endpoint(base_url, "/v1/messages"), headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, json=body)
            response.raise_for_status()
            content = response.json().get("content", [])
            text = "\n".join(str(item.get("text", "")) for item in content if item.get("type") == "text")
        elif protocol == "gemini":
            contents = [{"role": "model" if item.get("role") == "assistant" else "user", "parts": _gemini_parts(item.get("content"))} for item in messages]
            response = await client.post(_endpoint(base_url, f"/v1beta/models/{model}:generateContent"), params={"key": api_key}, json={"contents": contents})
            response.raise_for_status()
            text = "\n".join(str(part.get("text", "")) for part in response.json().get("candidates", [{}])[0].get("content", {}).get("parts", []))
        else:
            response = await client.post(_endpoint(base_url, "/v1/chat/completions"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "messages": messages})
            response.raise_for_status()
            text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    if not text:
        raise RuntimeError("AI 接口返回了空内容")
    return str(text)


async def call_provider(config: AIProviderConfig, snapshot: dict[str, Any]) -> str:
    protocol = "chat_completions" if config.interface_type == "compatible" else config.protocol
    return await _call_provider(
        base_url=config.base_url,
        model=config.model,
        protocol=protocol,
        timeout_seconds=config.timeout_seconds,
        api_key=decrypt_secret(config.encrypted_api_key),
        snapshot=snapshot,
    )


async def test_provider_values(
    *,
    base_url: str,
    model: str,
    protocol: str,
    timeout_seconds: int,
    api_key: str,
) -> str:
    return await _call_provider(
        base_url=base_url,
        model=model,
        protocol=protocol,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        snapshot={"测试": True, "说明": "只回复：连接成功"},
    )


async def test_provider(config: AIProviderConfig) -> str:
    return await call_provider(
        config,
        {"测试": True, "说明": "只回复：连接成功"},
    )


async def stream_chat_provider(
    config: AIProviderConfig, messages: list[dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """Yield assistant text from an OpenAI-compatible chat completion stream."""
    protocol = "chat_completions" if config.interface_type == "compatible" else config.protocol
    if protocol in {"anthropic", "gemini", "grok"}:
        async for part in _stream_native_provider(config, messages):
            yield part
        return
    api_key = decrypt_secret(config.encrypted_api_key)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": config.model, "messages": messages, "stream": True}
    if protocol == "responses":
        instructions, response_input = _responses_request(messages)
        body = {"model": config.model, "input": response_input, "stream": True}
        if instructions:
            body["instructions"] = instructions
    async with httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False) as client:
        endpoint = "responses" if protocol == "responses" else "chat/completions"
        for candidate in _base_candidates(config.base_url):
          async with client.stream("POST", _endpoint(candidate, f"/{endpoint}"), headers=headers, json=body) as response:
            if response.status_code == 404 and candidate != _base_candidates(config.base_url)[-1]:
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"AI 接口返回 {response.status_code}: {detail}") from exc
            if protocol == "responses":
                async for line in response.aiter_lines():
                    if line.startswith("data:") and line[5:].strip() not in {"", "[DONE]"}:
                        try:
                            payload = json.loads(line[5:].strip())
                            text = payload.get("delta") or payload.get("text") or ""
                            if text:
                                yield str(text)
                        except json.JSONDecodeError:
                            continue
            else:
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if value == "[DONE]":
                        break
                    try:
                        payload = json.loads(value)
                        text = payload.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if text:
                            yield str(text)
                    except (json.JSONDecodeError, IndexError, AttributeError, TypeError):
                        continue
            break


async def _stream_native_provider(config: AIProviderConfig, messages: list[dict[str, Any]]) -> AsyncGenerator[str, None]:
    api_key = decrypt_secret(config.encrypted_api_key)
    async with httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False) as client:
        if config.protocol == "anthropic":
            system = next((str(item["content"]) for item in messages if item.get("role") == "system"), None)
            body: dict[str, Any] = {"model": config.model, "max_tokens": 4096, "stream": True, "messages": [{**item, "content": _anthropic_content(item.get("content"))} for item in messages if item.get("role") != "system"]}
            if system:
                body["system"] = system
            stream_request = client.stream("POST", _endpoint(config.base_url, "/v1/messages"), headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, json=body)
        elif config.protocol == "gemini":
            contents = [{"role": "model" if item.get("role") == "assistant" else "user", "parts": _gemini_parts(item.get("content"))} for item in messages]
            stream_request = client.stream("POST", _endpoint(config.base_url, f"/v1beta/models/{config.model}:streamGenerateContent"), params={"alt": "sse", "key": api_key}, json={"contents": contents})
        else:
            stream_request = client.stream("POST", _endpoint(config.base_url, "/v1/chat/completions"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": config.model, "messages": messages, "stream": True})
        async with stream_request as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value in {"", "[DONE]"}:
                    continue
                try:
                    payload = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if config.protocol == "anthropic":
                    text = payload.get("delta", {}).get("text", "")
                elif config.protocol == "gemini":
                    text = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                else:
                    text = payload.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if text:
                    yield str(text)


async def list_provider_models(
    *, base_url: str, timeout_seconds: int, api_key: str, protocol: str = "chat_completions"
) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"} if protocol != "anthropic" else {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        response = None
        for candidate in _base_candidates(base_url):
            if protocol == "gemini":
                response = await client.get(_endpoint(candidate, "/v1beta/models"), params={"key": api_key}, headers={})
            else:
                response = await client.get(_endpoint(candidate, "/v1/models" if protocol == "anthropic" else "/models"), headers=headers)
            if response.status_code != 404:
                break
        assert response is not None
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"模型接口返回 {response.status_code}: {response.text[:500]}") from exc
    payload = response.json()
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if protocol == "gemini" and isinstance(payload, dict):
        rows = [{"id": str(row.get("name", "")).removeprefix("models/")} for row in payload.get("models", []) if isinstance(row, dict)]
    models = sorted(
        {str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")},
        key=str.casefold,
    )
    if not models:
        raise RuntimeError("模型接口未返回可用模型")
    return models
