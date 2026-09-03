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
# Keep background version checks reasonably fresh without hammering registries.
_VERSION_CACHE_TTL = 60.0
_version_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}


class UpdateRegistryError(RuntimeError):
    pass


class UpdateBusyError(RuntimeError):
    pass


def version_key(value: str) -> tuple[int, int, int]:
    match = SEMVER_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("无效的语义版本号")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


ALLOWED_REGISTRIES = {
    "docker.io": "Docker Hub",
    "crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com": "阿里云 ACR",
}
REGISTRY_REPOSITORIES = {
    "docker.io": "litehub/vx-data-watch",
    "crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com": "zhang_spaces/vx-data-watch",
}

def configured_registry() -> str:
    """Resolve the updater registry, correcting legacy env files by VX_IMAGE."""
    settings = get_settings()
    registry = getattr(settings, "update_registry", "docker.io")
    configured_path = Path(getattr(settings, "update_env_file", ".env"))
    path = configured_path if configured_path.is_file() else Path(".env")
    try:
        content = path.read_text(encoding="utf-8") if path.is_file() else ""
        image_match = re.search(r"(?m)^VX_IMAGE=([^\r\n]+)", content)
        image = image_match.group(1).strip() if image_match else ""
        acr_host = next((value for value in ALLOWED_REGISTRIES if value != "docker.io" and image.startswith(value + "/")), None)
        if acr_host:
            return acr_host
    except OSError:
        pass
    return registry


async def fetch_registry_versions(repository: str, registry: str = "docker.io") -> list[dict[str, Any]]:
    if registry not in ALLOWED_REGISTRIES:
        raise UpdateRegistryError("不支持的镜像仓库")
    urls = (
        [(f"https://hub.docker.com/v2/repositories/{repository}/tags", {"page_size": 100, "ordering": "last_updated"}),
         (f"https://registry-1.docker.io/v2/{repository}/tags/list", None)]
        if registry == "docker.io"
        else [(f"https://{registry}/v2/{repository}/tags/list", None)]
    )
    last_error: Exception | None = None
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            payload: dict[str, Any] | None = None
            for url, params in urls:
                for attempt in range(3):
                    try:
                        response = await client.get(url, params=params)
                        if response.status_code == 401:
                            challenge = response.headers.get("www-authenticate", "")
                            match = re.match(r"Bearer\s+(.+)", challenge, re.IGNORECASE)
                            if not match:
                                response.raise_for_status()
                            values = dict(re.findall(r'(\w+)="([^"]+)"', match.group(1)))
                            realm = values.get("realm")
                            if not realm:
                                response.raise_for_status()
                            token_response = await client.get(
                                realm,
                                params={key: value for key, value in values.items() if key in {"service", "scope"}},
                            )
                            token_response.raise_for_status()
                            token_payload = token_response.json()
                            token = token_payload.get("token") or token_payload.get("access_token")
                            if not isinstance(token, str) or not token:
                                raise UpdateRegistryError("镜像仓库认证响应缺少访问令牌")
                            response = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
                        response.raise_for_status()
                        decoded = response.json()
                        if not isinstance(decoded, dict):
                            raise ValueError("镜像仓库返回格式无效")
                        payload = decoded
                        break
                    except (httpx.HTTPError, ValueError, TypeError, UpdateRegistryError) as exc:
                        last_error = exc
                        if attempt < 2:
                            await asyncio.sleep(0.25 * (attempt + 1))
                if payload is not None:
                    break
            if payload is None:
                label = ALLOWED_REGISTRIES.get(registry, registry)
                raise UpdateRegistryError(
                    f"镜像仓库 {registry}（{label}）不可用，无法获取版本信息；请检查服务器网络、镜像源可用性或仓库权限"
                ) from last_error
    except UpdateRegistryError:
        cached = _version_cache.get((registry, repository))
        if cached and time.monotonic() - cached[0] <= _VERSION_CACHE_TTL:
            return cached[1]
        raise

    versions: list[dict[str, Any]] = []
    rows = payload.get("results", []) if "results" in payload else [{"name": name} for name in payload.get("tags", [])]
    for row in rows:
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
    _version_cache[(registry, repository)] = (time.monotonic(), versions)
    return versions


def version_payload(versions: list[dict[str, Any]], registry: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    selected_registry = registry or configured_registry()
    repository = REGISTRY_REPOSITORIES.get(selected_registry, settings.update_repository)
    selectable = [row for row in versions if row["version"] != __version__]
    image_repository = f"{selected_registry}/{repository}:latest"
    return {
        "current_version": __version__,
        "latest_version": versions[0]["version"] if versions else None,
        "versions": selectable,
        "repository": image_repository,
        "registry": selected_registry,
        "configured_registry": configured_registry(),
        "registries": [{"registry": key, "label": label, "repository": f"{key}/{REGISTRY_REPOSITORIES[key]}:latest"} for key, label in ALLOWED_REGISTRIES.items()],
        "update_supported": settings.updater_enabled,
        "deployment": "docker" if settings.updater_enabled else "source",
    }


def save_update_registry(registry: str) -> None:
    """Persist the selected registry in the deployment .env file."""
    if registry not in ALLOWED_REGISTRIES:
        raise UpdateRegistryError("不支持的镜像仓库")
    settings = get_settings()
    path = settings.update_env_file
    if not path.is_file() and Path(".env").is_file():
        path = Path(".env")
    if not path.is_file():
        raise UpdateRegistryError("找不到部署配置文件 .env，无法保存镜像源")
    try:
        content = path.read_text(encoding="utf-8")
        line = f"VX_UPDATE_REGISTRY={registry}"
        if re.search(r"(?m)^VX_UPDATE_REGISTRY=.*$", content):
            content = re.sub(r"(?m)^VX_UPDATE_REGISTRY=.*$", line, content)
        else:
            content = content.rstrip("\r\n") + "\n" + line + "\n"
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
        settings.update_registry = registry
    except OSError as exc:
        raise UpdateRegistryError(f"保存镜像源配置失败：{exc}") from exc


def _update_dir() -> Path:
    path = get_settings().data_dir / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_update_dir_for_app(path: Path | None = None) -> Path:
    """Create the shared update directory and make it writable by the app user.

    The updater runs as root so it can access Docker, while the API runs as
    UID 10001. Named volumes otherwise may be initialized as root-owned when
    the updater starts first, preventing the API from queueing an update.
    """
    directory = path or _update_dir()
    directory.mkdir(parents=True, exist_ok=True)
    geteuid = getattr(os, "geteuid", None)
    chown = getattr(os, "chown", None)
    if not callable(geteuid) or not callable(chown) or geteuid() != 0:
        return directory
    try:
        uid = int(os.environ.get("VX_APP_UID", "10001"))
        gid = int(os.environ.get("VX_APP_GID", str(uid)))
        chown(directory, uid, gid)
        directory.chmod(0o770)
    except (OSError, ValueError):
        # A non-Linux development environment may not support ownership changes.
        pass
    return directory


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


def queue_update(version: str, backup_filename: str, registry: str = "docker.io") -> dict[str, Any]:
    request_path, processing_path, status_path = update_paths()
    status = read_update_status()
    if request_path.exists() or processing_path.exists() or status.get("state") in ACTIVE_STATES:
        raise UpdateBusyError("已有更新任务正在执行")
    request = {
        "id": uuid.uuid4().hex,
        "version": version,
        "repository": REGISTRY_REPOSITORIES.get(registry, get_settings().update_repository),
        "registry": registry,
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
