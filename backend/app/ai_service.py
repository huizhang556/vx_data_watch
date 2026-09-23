from __future__ import annotations

import json
import asyncio
import ipaddress
import socket
import base64
from urllib.parse import urlsplit
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from .models import AIProviderConfig
from .ai_catalog import load_catalog
from .security import decrypt_secret
from .ai_protocol_registry import (
    CHAT_PROTOCOL_HANDLERS,
    SUPPORTED_CHAT_PROTOCOLS,
    SUPPORTED_IMAGE_PROTOCOLS,
    SUPPORTED_VIDEO_PROTOCOLS,
)

SYSTEM_PROMPT = """你是视频号数据分析顾问。只依据用户提供的结构化数据分析，不得编造完播率、受众画像、流量来源或其他缺失指标。
输出必须包含：数据观察、异常与趋势、高贡献视频、可能原因、优化建议、验证方法、数据限制。
把推测明确标为推测，建议要具体且可验证。使用简体中文 Markdown；可使用标题、列表、表格和强调，不要输出 HTML 或脚本。"""


CHAT_TEST_PROMPT = "请简要回复：连接测试成功。"
IMAGE_TEST_PROMPT = "一个简洁的蓝色几何图标，白色背景。"
VIDEO_TEST_PROMPT = "蓝色光点缓慢移动，固定镜头，短视频。"


def _base_candidates(base_url: str) -> list[str]:
    """Try the common OpenAI-compatible root and /v1 forms without UI suffixes."""
    base = base_url.strip().rstrip("/")
    path = base.split("?", 1)[0].rstrip("/").lower()
    if path.endswith(("/v1", "/v2")):
        return [base]
    return [f"{base}/v1", base]


def _endpoint(base_url: str, suffix: str) -> str:
    _validate_provider_url_secure(base_url)
    return base_url.rstrip("/") + suffix


def _validate_provider_url(base_url: str) -> None:
    """Reject obvious SSRF targets before making an outbound provider call."""
    _validate_provider_url_secure(base_url)
    return
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"https", "http"} or not host:
        raise ValueError("AI 接口地址无效")
    if host in {"localhost", "localhost.localdomain", "metadata.google.internal", "instance-data"}:
        raise ValueError("AI 接口地址不允许指向本机或云元数据服务")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if address.is_loopback or address.is_private or address.is_link_local or address.is_reserved or address.is_unspecified:
        raise ValueError("AI 接口地址不允许指向内网或保留地址")


def _validate_provider_url_secure(base_url: str) -> None:
    """Reject private DNS answers as well as literal private addresses."""
    parsed = urlsplit(base_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"https", "http"} or not host:
        raise ValueError("Invalid AI provider URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Invalid AI provider URL")
    if host in {"localhost", "localhost.localdomain", "metadata.google.internal", "instance-data"}:
        raise ValueError("AI provider URL points to a local or metadata service")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            addresses = {
                ipaddress.ip_address(row[4][0])
                for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                if row[4] and row[4][0]
            }
        except (OSError, ValueError):
            raise ValueError("AI provider hostname could not be resolved") from None
    if not addresses or any(
        address.is_loopback or address.is_private or address.is_link_local
        or address.is_reserved or address.is_unspecified
        for address in addresses
    ):
        raise ValueError("AI provider URL points to a private or reserved address")


def _raise_for_provider_response(response: httpx.Response) -> None:
    """Reject redirects explicitly, even though clients disable following them."""
    if 300 <= response.status_code < 400:
        raise RuntimeError("AI provider redirects are not allowed")
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = response.text[:500]
        raise RuntimeError(f"AI provider returned {response.status_code}: {detail}") from exc


def _configured_protocol(config: AIProviderConfig, model: str | None = None) -> str:
    try:
        mappings = json.loads(config.model_protocols_json) if config.model_protocols_json else {}
    except (TypeError, ValueError):
        mappings = {}
    selected = mappings.get(model or config.model) if isinstance(mappings, dict) else None
    if selected in SUPPORTED_CHAT_PROTOCOLS:
        return selected
    return "chat_completions" if config.interface_type == "compatible" else config.protocol


def _catalog_protocol_path(base_url: str, protocol: str, model: str | None = None, category: str = "chat") -> str | None:
    """Resolve an official protocol path from the shipped public catalog."""
    try:
        payload = load_catalog()[0]
    except (OSError, TypeError):
        return None
    normalized = base_url.rstrip("/").lower()
    for provider in (payload.get("providers", {}) if isinstance(payload, dict) else {}).values():
        if not isinstance(provider, dict) or not normalized.startswith(str(provider.get("base_url", "")).rstrip("/").lower()):
            continue
        for item in provider.get("protocols", {}).get(category, []):
            if isinstance(item, dict) and item.get("id") == protocol and item.get("implemented", True) and not item.get("disabled", False):
                path = str(item.get("path") or "")
                return path.replace("{model}", model or "")
    return None


def _request_path(base_url: str, protocol: str, model: str | None = None, category: str = "chat") -> str:
    configured = _catalog_protocol_path(base_url, protocol, model, category)
    if configured:
        root = base_url.rstrip("/").lower()
        for prefix in ("/v1", "/v2"):
            if root.endswith(prefix) and configured.startswith(f"{prefix}/"):
                return configured[len(prefix):]
        return configured
    if protocol == "responses":
        return "/responses" if base_url.rstrip("/").lower().endswith(("/v1", "/v2")) else "/v1/responses"
    if protocol == "gemini":
        return f"/v1beta/models/{model or ''}:generateContent"
    if protocol == "anthropic":
        return "/v1/messages"
    if protocol == "openai_images":
        return "/images/generations" if base_url.rstrip("/").lower().endswith(("/v1", "/v2")) else "/v1/images/generations"
    if protocol == "openai_videos":
        return "/videos" if base_url.rstrip("/").lower().endswith(("/v1", "/v2")) else "/v1/videos"
    return "/chat/completions" if base_url.rstrip("/").lower().endswith(("/v1", "/v2")) else "/v1/chat/completions"


def build_prompt(snapshot: dict[str, Any]) -> str:
    return "请分析以下视频号数据：\n" + json.dumps(snapshot, ensure_ascii=False)


def provider_request_preview(base_url: str, model: str, protocol: str, api_key: str) -> dict[str, Any]:
    """Return the sanitized request shape shown in the configuration tester."""
    prompt = CHAT_TEST_PROMPT if protocol in SUPPORTED_IMAGE_PROTOCOLS | SUPPORTED_VIDEO_PROTOCOLS else build_prompt({"测试": True, "说明": CHAT_TEST_PROMPT})
    if protocol in SUPPORTED_IMAGE_PROTOCOLS:
        path = _request_path(base_url, protocol, model, "image")
        body: dict[str, Any] = {"model": model, "prompt": IMAGE_TEST_PROMPT, "n": 1, "size": "1024x1024", "response_format": "b64_json"}
    elif protocol in SUPPORTED_VIDEO_PROTOCOLS:
        path = _request_path(base_url, protocol, model, "video")
        body = {"model": model, "prompt": VIDEO_TEST_PROMPT}
    elif protocol == "responses":
        path = _request_path(base_url, protocol, model)
        body: dict[str, Any] = {"model": model, "instructions": SYSTEM_PROMPT, "input": prompt}
    elif protocol == "anthropic":
        path = _request_path(base_url, protocol, model)
        body = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]}
    elif protocol == "gemini":
        path = _request_path(base_url, protocol, model)
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    else:
        path = _request_path(base_url, protocol, model)
        body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    endpoint = _base_candidates(base_url)[0].rstrip("/") + path
    return {
        "method": "POST",
        "url": endpoint,
        "protocol": protocol,
        "model": model,
        "headers": {"Authorization": "Bearer ********"} if protocol not in {"anthropic", "gemini"} else ({"x-api-key": "********"} if protocol == "anthropic" else {}),
        "body": body,
        "api_key_query": "********" if protocol == "gemini" else None,
    }


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
) -> str | dict[str, Any]:
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
            response = await client.post(_endpoint(candidate, _request_path(candidate, protocol, model)), headers=headers, json=body)
            if response.status_code != 404:
                break
        assert response is not None
    try:
        _raise_for_provider_response(response)
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
            response = await client.post(_endpoint(base_url, _request_path(base_url, protocol, model)), headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, json=body)
            _raise_for_provider_response(response)
            content = response.json().get("content", [])
            text = "\n".join(str(item.get("text", "")) for item in content if item.get("type") == "text")
        elif protocol == "gemini":
            contents = [{"role": "model" if item.get("role") == "assistant" else "user", "parts": _gemini_parts(item.get("content"))} for item in messages]
            response = await client.post(_endpoint(base_url, _request_path(base_url, protocol, model)), params={"key": api_key}, json={"contents": contents})
            _raise_for_provider_response(response)
            text = "\n".join(str(part.get("text", "")) for part in response.json().get("candidates", [{}])[0].get("content", {}).get("parts", []))
        else:
            response = await client.post(_endpoint(base_url, _request_path(base_url, protocol, model)), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "messages": messages})
            _raise_for_provider_response(response)
            text = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    if not text:
        raise RuntimeError("AI 接口返回了空内容")
    return str(text)


async def call_provider(config: AIProviderConfig, snapshot: dict[str, Any]) -> str:
    protocol = _configured_protocol(config)
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
    if protocol in SUPPORTED_IMAGE_PROTOCOLS:
        base = _base_candidates(base_url)[0]
        body = {"model": model, "prompt": IMAGE_TEST_PROMPT, "n": 1, "size": "1024x1024", "response_format": "b64_json"}
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            response = await client.post(_endpoint(base, _request_path(base, protocol, model, "image")), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body)
            _raise_for_provider_response(response)
        return "生图测试请求已成功，接口返回正常。"
    if protocol in SUPPORTED_VIDEO_PROTOCOLS:
        base = _base_candidates(base_url)[0]
        body = {"model": model, "prompt": VIDEO_TEST_PROMPT}
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
            response = await client.post(_endpoint(base, _request_path(base, protocol, model, "video")), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=body)
            _raise_for_provider_response(response)
        payload = response.json()
        task_id = payload.get("id") if isinstance(payload, dict) else None
        return f"生视频任务创建成功，任务 ID：{task_id or '上游未返回任务 ID'}"
    return await _call_provider(
        base_url=base_url,
        model=model,
        protocol=protocol,
        timeout_seconds=timeout_seconds,
        api_key=api_key,
        snapshot={"测试": True, "说明": CHAT_TEST_PROMPT},
    )


async def test_image_preview(
    *,
    base_url: str,
    model: str,
    protocol: str,
    timeout_seconds: int,
    api_key: str,
) -> dict[str, Any]:
    """Run an image test and return a browser-previewable result."""
    if protocol not in SUPPORTED_IMAGE_PROTOCOLS:
        raise ValueError("image protocol is not supported")
    base = _base_candidates(base_url)[0]
    body = {"model": model, "prompt": IMAGE_TEST_PROMPT, "n": 1, "size": "1024x1024", "response_format": "b64_json"}
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        response = await client.post(
            _endpoint(base, _request_path(base, protocol, model, "image")),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
        _raise_for_provider_response(response)
    payload = response.json()
    items = payload.get("data") if isinstance(payload, dict) else None
    item = items[0] if isinstance(items, list) and items else None
    if not isinstance(item, dict):
        raise RuntimeError("image provider returned no image")
    encoded = item.get("b64_json")
    if isinstance(encoded, str) and encoded:
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("image response encoding is invalid") from exc
        if not raw or len(raw) > 20 * 1024 * 1024:
            raise RuntimeError("generated image size is invalid")
        return {"text": "image test request succeeded", "media": {"kind": "image", "data_url": f"data:image/png;base64,{base64.b64encode(raw).decode('ascii')}"}}
    image_url = item.get("url")
    if isinstance(image_url, str) and image_url.startswith(("https://", "http://")):
        _validate_provider_url_secure(image_url)
        return {"text": "image test request succeeded", "media": {"kind": "image", "url": image_url}}
    raise RuntimeError("image provider returned no previewable image")


async def test_provider(config: AIProviderConfig) -> str:
    return await call_provider(
        config,
        {"测试": True, "说明": "只回复：连接成功"},
    )


async def generate_image_provider(
    config: AIProviderConfig,
    prompt: str,
    model: str,
    protocol: str,
) -> bytes:
    """Generate one image using a verified synchronous image protocol."""
    if protocol not in SUPPORTED_IMAGE_PROTOCOLS:
        raise ValueError("当前生图协议尚未接入")
    if protocol != "openai_images":
        raise ValueError("当前生图协议尚未接入")
    api_key = decrypt_secret(config.encrypted_api_key)
    body = {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024", "response_format": "b64_json"}
    async with httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False) as client:
        response = None
        for candidate in _base_candidates(config.base_url):
            response = await client.post(
                _endpoint(candidate, _request_path(candidate, protocol, model, "image")),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
            )
            if response.status_code != 404 or candidate == _base_candidates(config.base_url)[-1]:
                break
        if response is None:
            raise RuntimeError("生图接口无响应")
        _raise_for_provider_response(response)
        payload = response.json()
    items = payload.get("data") if isinstance(payload, dict) else None
    item = items[0] if isinstance(items, list) and items else None
    if not isinstance(item, dict):
        raise RuntimeError("生图接口返回格式无效")
    encoded = item.get("b64_json")
    if isinstance(encoded, str) and encoded:
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("生图接口返回的图片编码无效") from exc
    else:
        image_url = item.get("url")
        if not isinstance(image_url, str) or not image_url.startswith(("https://", "http://")):
            raise RuntimeError("生图接口未返回可保存的图片数据")
        _validate_provider_url_secure(image_url)
        async with httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False) as download_client:
            image_response = await download_client.get(image_url)
            _raise_for_provider_response(image_response)
            if not image_response.headers.get("content-type", "").lower().startswith("image/"):
                raise RuntimeError("生图接口返回的 URL 不是图片")
            data = image_response.content
    if not data or len(data) > 20 * 1024 * 1024:
        raise RuntimeError("生成图片大小无效")
    return data


async def generate_video_provider(
    config: AIProviderConfig,
    prompt: str,
    model: str,
    protocol: str,
) -> tuple[bytes, str, str]:
    """Create, poll, and download one video using OpenAI's async task API."""
    if protocol not in SUPPORTED_VIDEO_PROTOCOLS:
        raise ValueError("当前生视频协议尚未接入")
    api_key = decrypt_secret(config.encrypted_api_key)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    deadline = asyncio.get_running_loop().time() + config.timeout_seconds
    async with httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False) as client:
        candidates = _base_candidates(config.base_url)
        response = None
        for candidate in candidates:
            response = await client.post(
                _endpoint(candidate, _request_path(candidate, protocol, model, "video")),
                headers=headers,
                json={"model": model, "prompt": prompt},
            )
            if response.status_code != 404 or candidate == candidates[-1]:
                break
        if response is None:
            raise RuntimeError("生视频接口无响应")
        _raise_for_provider_response(response)
        task = response.json()
        task_id = task.get("id") if isinstance(task, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError("生视频接口未返回任务 ID")
        poll_delay = 1.0
        while True:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("生视频任务等待超时")
            await asyncio.sleep(min(poll_delay, max(0.1, deadline - asyncio.get_running_loop().time())))
            poll_delay = min(5.0, poll_delay + 0.5)
            status_response = await client.get(
                _endpoint(candidates[0], f"/videos/{task_id}"),
                headers={"Authorization": f"Bearer {api_key}"},
            )
            _raise_for_provider_response(status_response)
            status_payload = status_response.json()
            status = str(status_payload.get("status", "")).lower()
            if status in {"failed", "cancelled", "canceled"}:
                raise RuntimeError(str(status_payload.get("error") or "生视频任务失败"))
            if status in {"completed", "succeeded", "success"}:
                break
        content_response = await client.get(
            _endpoint(candidates[0], f"/videos/{task_id}/content"),
            headers={"Authorization": f"Bearer {api_key}"},
        )
        _raise_for_provider_response(content_response)
        data = content_response.content
        content_type = content_response.headers.get("content-type", "video/mp4").split(";", 1)[0].lower()
    if not data or len(data) > 200 * 1024 * 1024:
        raise RuntimeError("生成视频大小无效")
    if not content_type.startswith("video/"):
        content_type = "video/mp4"
    if content_type == "video/mp4" and b"ftyp" not in data[:64]:
        raise RuntimeError("上游返回的 MP4 文件格式无效")
    if content_type == "video/webm" and not data.startswith(b"\x1a\x45\xdf\xa3"):
        raise RuntimeError("上游返回的 WebM 文件格式无效")
    return data, content_type, task_id


async def stream_chat_provider(
    config: AIProviderConfig, messages: list[dict[str, Any]], model: str | None = None, protocol: str | None = None
) -> AsyncGenerator[str, None]:
    """Yield assistant text from an OpenAI-compatible chat completion stream."""
    selected_model = model or config.model
    selected_protocol = protocol or _configured_protocol(config, selected_model)
    if selected_protocol in {"anthropic", "gemini", "grok"}:
        async for part in _stream_native_provider(config, messages, selected_protocol, selected_model):
            yield part
        return
    api_key = decrypt_secret(config.encrypted_api_key)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": selected_model, "messages": messages, "stream": True}
    if selected_protocol == "responses":
        instructions, response_input = _responses_request(messages)
        body = {"model": selected_model, "input": response_input, "stream": True}
        if instructions:
            body["instructions"] = instructions
    async with httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False) as client:
        for candidate in _base_candidates(config.base_url):
          async with client.stream("POST", _endpoint(candidate, _request_path(candidate, selected_protocol, selected_model)), headers=headers, json=body) as response:
            if response.status_code == 404 and candidate != _base_candidates(config.base_url)[-1]:
                continue
            try:
                _raise_for_provider_response(response)
            except httpx.HTTPStatusError as exc:
                detail = (await response.aread()).decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"AI 接口返回 {response.status_code}: {detail}") from exc
            if selected_protocol == "responses":
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


async def _stream_native_provider(
    config: AIProviderConfig,
    messages: list[dict[str, Any]],
    protocol: str | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    api_key = decrypt_secret(config.encrypted_api_key)
    selected_protocol = protocol or config.protocol
    selected_model = model or config.model
    async with httpx.AsyncClient(timeout=config.timeout_seconds, follow_redirects=False) as client:
        if selected_protocol == "anthropic":
            system = next((str(item["content"]) for item in messages if item.get("role") == "system"), None)
            body: dict[str, Any] = {"model": selected_model, "max_tokens": 4096, "stream": True, "messages": [{**item, "content": _anthropic_content(item.get("content"))} for item in messages if item.get("role") != "system"]}
            if system:
                body["system"] = system
            stream_request = client.stream("POST", _endpoint(config.base_url, _request_path(config.base_url, selected_protocol, selected_model)), headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, json=body)
        elif selected_protocol == "gemini":
            contents = [{"role": "model" if item.get("role") == "assistant" else "user", "parts": _gemini_parts(item.get("content"))} for item in messages]
            stream_path = _request_path(config.base_url, selected_protocol, selected_model).replace(":generateContent", ":streamGenerateContent")
            stream_request = client.stream("POST", _endpoint(config.base_url, stream_path), params={"alt": "sse", "key": api_key}, json={"contents": contents})
        else:
            stream_request = client.stream("POST", _endpoint(config.base_url, _request_path(config.base_url, selected_protocol, selected_model)), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": selected_model, "messages": messages, "stream": True})
        async with stream_request as response:
            _raise_for_provider_response(response)
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
                if selected_protocol == "anthropic":
                    text = payload.get("delta", {}).get("text", "")
                elif selected_protocol == "gemini":
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
        _raise_for_provider_response(response)
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
