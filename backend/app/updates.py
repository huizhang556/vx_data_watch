from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .config import get_settings

SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ACTIVE_STATES = {"queued", "pulling", "restarting", "verifying", "rolling_back"}
_VERSION_CACHE_TTL = 600.0
_version_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


class UpdateRegistryError(RuntimeError):
    pass


class UpdateBusyError(RuntimeError):
    pass


def version_key(value: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("无效的语义版本号")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


async def fetch_registry_versions(repository: str) -> list[dict[str, Any]]:
    url = f"https://hub.docker.com/v2/repositories/{repository}/tags"
    last_error: Exception | None = None
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            for attempt in range(3):
                try:
                    response = await client.get(
                        url, params={"page_size": 100, "ordering": "last_updated"}
                    )
                    response.raise_for_status()
                    payload = response.json()
                    break
                except (httpx.HTTPError, ValueError, TypeError) as exc:
                    last_error = exc
                    if attempt < 2:
                        await asyncio.sleep(0.25 * (attempt + 1))
            else:
                raise UpdateRegistryError("无法连接 Docker Hub 获取版本信息") from last_error
    except UpdateRegistryError:
        cached = _version_cache.get(repository)
        if cached and time.monotonic() - cached[0] <= _VERSION_CACHE_TTL:
            return cached[1]
        raise

    versions: list[dict[str, Any]] = []
    for row in payload.get("results", []):
        name = row.get("name")
        if not isinstance(name, str) or not SEMVER_PATTERN.fullmatch(name):
            continue
        versions.append(
            {
                "version": name,
                "published_at": row.get("last_updated"),
                "digest": row.get("digest"),
            }
        )
    versions.sort(key=lambda row: version_key(row["version"]), reverse=True)
    _version_cache[repository] = (time.monotonic(), versions)
    return versions


def version_payload(versions: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    selectable = [row for row in versions if row["version"] != __version__]
    return {
        "current_version": __version__,
        "latest_version": versions[0]["version"] if versions else None,
        "versions": selectable,
        "repository": settings.update_repository,
        "update_supported": settings.updater_enabled,
        "deployment": "docker" if settings.updater_enabled else "source",
    }


def _update_dir() -> Path:
    path = get_settings().data_dir / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def update_paths() -> tuple[Path, Path, Path]:
    directory = _update_dir()
    return directory / "request.json", directory / "processing.json", directory / "status.json"


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def read_update_status() -> dict[str, Any]:
    _, _, status_path = update_paths()
    if not status_path.is_file():
        return {"state": "idle", "current_version": __version__}
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"state": "idle"}
    except (OSError, json.JSONDecodeError):
        return {"state": "unknown", "message": "更新状态文件不可读"}


def queue_update(version: str, backup_filename: str) -> dict[str, Any]:
    request_path, processing_path, status_path = update_paths()
    status = read_update_status()
    if request_path.exists() or processing_path.exists() or status.get("state") in ACTIVE_STATES:
        raise UpdateBusyError("已有更新任务正在执行")
    request = {
        "id": uuid.uuid4().hex,
        "version": version,
        "repository": get_settings().update_repository,
        "backup_filename": backup_filename,
        "requested_at": datetime.now(UTC).isoformat(),
    }
    try:
        descriptor = os.open(request_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise UpdateBusyError("已有更新任务正在排队") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(request, handle, ensure_ascii=False)
    write_json_atomic(
        status_path,
        {
            "id": request["id"],
            "state": "queued",
            "target_version": version,
            "current_version": __version__,
            "message": "更新任务已排队",
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
    return request
