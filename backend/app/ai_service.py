from __future__ import annotations

import json
from typing import Any

import httpx

from .models import AIProviderConfig
from .security import decrypt_secret

SYSTEM_PROMPT = """你是视频号数据分析顾问。只依据用户提供的结构化数据分析，不得编造完播率、受众画像、流量来源或其他缺失指标。
输出必须包含：数据观察、异常与趋势、高贡献视频、可能原因、优化建议、验证方法、数据限制。
把推测明确标为推测，建议要具体且可验证。使用简体中文 Markdown；可使用标题、列表、表格和强调，不要输出 HTML 或脚本。"""


def _endpoint(base_url: str, suffix: str) -> str:
    base = base_url.rstrip("/")
    return base + suffix


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
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    user_content = "请分析以下视频号数据：\n" + json.dumps(snapshot, ensure_ascii=False)
    if protocol == "responses":
        url = _endpoint(base_url, "/responses")
        body = {
            "model": model,
            "instructions": SYSTEM_PROMPT,
            "input": user_content,
        }
    else:
        url = _endpoint(base_url, "/chat/completions")
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        response = await client.post(url, headers=headers, json=body)
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


async def call_provider(config: AIProviderConfig, snapshot: dict[str, Any]) -> str:
    return await _call_provider(
        base_url=config.base_url,
        model=config.model,
        protocol=config.protocol,
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


async def list_provider_models(
    *, base_url: str, timeout_seconds: int, api_key: str
) -> list[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
        response = await client.get(_endpoint(base_url, "/models"), headers=headers)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"模型接口返回 {response.status_code}: {response.text[:500]}") from exc
    payload = response.json()
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    models = sorted(
        {str(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")},
        key=str.casefold,
    )
    if not models:
        raise RuntimeError("模型接口未返回可用模型")
    return models
