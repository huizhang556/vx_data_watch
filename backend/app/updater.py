from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .config import get_settings
from .docker_engine import DockerEngine
from .updates import (
    ALLOWED_REGISTRIES,
    REGISTRY_REPOSITORIES,
    SEMVER_PATTERN,
    prepare_update_dir_for_app,
    update_paths,
    update_history_dir,
    write_json_atomic,
)


def _status(request: dict[str, Any], state: str, message: str, **extra: Any) -> None:
    _, _, status_path = update_paths()
    payload = {
            "id": request.get("id"),
            "state": state,
            "target_version": request.get("version"),
            "current_version": request.get("current_version", __version__),
            "registry": request.get("registry"),
            "repository": request.get("repository"),
            "image": request.get("image"),
            "deployment_method": request.get("deployment_method"),
            "backup_filename": request.get("backup_filename"),
            "started_at": request.get("requested_at"),
            "message": message,
            "updated_at": datetime.now(UTC).isoformat(),
            **extra,
        }
    try:
        started = datetime.fromisoformat(str(payload["started_at"]))
        payload["duration_seconds"] = max(0, round((datetime.now(UTC) - started).total_seconds(), 2))
    except (TypeError, ValueError):
        pass
    write_json_atomic(
        status_path,
        payload,
    )
    request_id = request.get("id")
    if isinstance(request_id, str) and request_id:
        history_path = update_history_dir() / f"{request_id}.json"
        try:
            history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.is_file() else {"id": request_id, "target_version": request.get("version"), "started_at": request.get("requested_at"), "stages": []}
            history.setdefault("stages", []).append({"state": state, "message": message, "at": payload["updated_at"]})
            history.update({key: value for key, value in request.items() if key != "version"})
            history.update(payload)
            if state == "success":
                history["final_version"] = extra.get("current_version", request.get("version"))
            if state == "rolling_back":
                history["rollback"] = True
            write_json_atomic(history_path, history)
        except (OSError, json.JSONDecodeError, TypeError):
            pass


def _persist_image(env_file: Path, image: str) -> None:
    content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    lines = content.splitlines()
    replacement = f"VX_IMAGE={image}"
    for index, line in enumerate(lines):
        if line.startswith("VX_IMAGE=") or line.startswith("# VX_IMAGE="):
            lines[index] = replacement
            break
    else:
        lines.append(replacement)
    env_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _rollback_record_path() -> Path:
    request_path, _, _ = update_paths()
    return request_path.with_name("rollback.json")


def _write_rollback_record(request: dict[str, Any], previous_env: str, image: str) -> None:
    write_json_atomic(
        _rollback_record_path(),
        {
            "request_id": request.get("id"),
            "previous_version": __version__,
            "previous_image": image,
            "previous_env": previous_env,
            "recorded_at": datetime.now(UTC).isoformat(),
        },
    )


def _cleanup_old_release_tags(
    docker: DockerEngine, repository: str, keep_versions: set[str]
) -> None:
    """Keep latest and the current/rollback releases; remove older local tags.

    Cleanup is best effort. A tag referenced by another container is left in
    place by Docker, and cleanup failure must never turn a successful update
    into a failed update.
    """
    try:
        tags = docker.image_tags(repository)
    except Exception:
        return
    for tag in tags:
        if tag == "latest" or tag in keep_versions or not SEMVER_PATTERN.fullmatch(tag):
            continue
        try:
            docker.remove_image(f"{repository}:{tag}")
        except Exception:
            continue


def process_update(request: dict[str, Any], engine: DockerEngine | None = None) -> None:
    settings = get_settings()
    version = request.get("version")
    repository = request.get("repository")
    registry = request.get("registry", "docker.io")
    if not isinstance(version, str) or not SEMVER_PATTERN.fullmatch(version):
        raise ValueError("更新版本号无效")
    expected_repository = REGISTRY_REPOSITORIES.get(registry, settings.update_repository)
    if repository != expected_repository or registry not in ALLOWED_REGISTRIES:
        raise ValueError("更新镜像仓库不在允许列表中")
    docker = engine or DockerEngine()
    env_existed = settings.update_env_file.exists()
    previous_env = (
        settings.update_env_file.read_text(encoding="utf-8") if env_existed else ""
    )
    previous_image = next(
        (line.partition("=")[2].strip() for line in previous_env.splitlines() if line.startswith("VX_IMAGE=")),
        "",
    )
    _write_rollback_record(request, previous_env, previous_image)
    _status(request, "pulling", "正在拉取目标镜像")
    pull_repository = repository if registry == "docker.io" else f"{registry}/{repository}"
    image_repository = f"docker.io/{repository}" if registry == "docker.io" else pull_repository
    latest_image = f"{image_repository}:latest"
    previous_version = __version__
    # Preserve the currently running release as the single local rollback tag
    # before replacing latest with the target image.
    if SEMVER_PATTERN.fullmatch(previous_version) and previous_version != version:
        try:
            docker.tag(latest_image, image_repository, previous_version)
        except Exception:
            pass
    docker.pull(pull_repository, version)
    inspect_image = getattr(docker, "image_inspect", None)
    target_metadata = inspect_image(f"{pull_repository}:{version}") if callable(inspect_image) else {}
    target_digest = next(iter(target_metadata.get("RepoDigests") or []), None)
    expected_digest = request.get("digest")
    if expected_digest:
        actual_digest = target_digest.rsplit("@", 1)[-1] if isinstance(target_digest, str) and "@" in target_digest else None
        if actual_digest != expected_digest:
            raise ValueError("目标镜像摘要与版本仓库记录不一致，已终止更新")
    # Keep deployment configuration on stable latest while pulling immutable
    # release tags. The companion updater is recreated after app replacement
    # so both services run the same image digest.
    source_image = f"{pull_repository}:{version}"
    docker.tag(source_image, image_repository, "latest")
    latest_metadata = inspect_image(latest_image) if callable(inspect_image) else {}
    latest_digest = next(iter(latest_metadata.get("RepoDigests") or []), None)
    _persist_image(settings.update_env_file, latest_image)
    _status(request, "restarting", "正在替换并重启应用", target_digest=target_digest, latest_digest=latest_digest, app_updater_digest_match=True)
    companion_id: str | None = None
    try:
        compose_repository = image_repository
        docker.replace_compose_service(
            settings.update_project, settings.update_service, compose_repository, "latest"
        )
        if settings.update_service != "updater":
            companion_id = docker.replace_running_companion(
                settings.update_project, "updater", compose_repository, "latest"
            )
    except Exception:
        _status(request, "rolling_back", "更新失败，正在恢复原版本")
        if env_existed:
            settings.update_env_file.write_text(previous_env, encoding="utf-8")
        else:
            settings.update_env_file.unlink(missing_ok=True)
        raise
    _rollback_record_path().unlink(missing_ok=True)
    _status(request, "success", "更新完成", current_version=version)
    if companion_id:
        docker.remove(companion_id, force=True)
    _cleanup_old_release_tags(docker, image_repository, {previous_version, version})


def process_config_migration(request: dict[str, Any], engine: DockerEngine | None = None) -> None:
    """Restart Docker deployments after config migration, restoring backups on failure."""
    settings = get_settings()
    if request.get("deployment_method") not in {"script", "compose"}:
        _status(request, "success", "源码部署无需 Docker 重启")
        return
    docker = engine or DockerEngine()
    repository = f"{settings.update_registry}/{settings.update_repository}" if settings.update_registry != "docker.io" else f"docker.io/{settings.update_repository}"
    _status(request, "restarting", "配置迁移完成，正在重建应用服务")
    companion_id: str | None = None
    try:
        docker.replace_compose_service(settings.update_project, settings.update_service, repository, "latest")
        if settings.update_service != "updater":
            companion_id = docker.replace_running_companion(settings.update_project, "updater", repository, "latest")
        _status(request, "success", "配置迁移完成，服务健康检查通过", current_version=__version__)
    except Exception:
        _status(request, "rolling_back", "配置迁移后的服务重启失败，正在恢复配置")
        backup_path = Path(str(request.get("backup_path", "")))
        env_path = settings.update_env_file
        if backup_path.is_file():
            env_path.write_bytes(backup_path.read_bytes())
        compose_backup = Path(str(request.get("compose_backup_path", "")))
        compose_path = env_path.parent / "docker-compose.yaml"
        if compose_backup.is_file():
            compose_path.write_bytes(compose_backup.read_bytes())
        raise
    finally:
        if companion_id:
            try:
                docker.remove(companion_id, force=True)
            except Exception:
                pass


def run() -> None:
    prepare_update_dir_for_app()
    request_path, processing_path, _ = update_paths()
    while True:
        if request_path.exists() and not processing_path.exists():
            request: dict[str, Any] = {}
            try:
                request_path.replace(processing_path)
                request = json.loads(processing_path.read_text(encoding="utf-8"))
                if request.get("type") == "config_migration":
                    process_config_migration(request)
                else:
                    process_update(request)
            except Exception as exc:
                _status(request, "failed", f"更新失败：{exc}")
            finally:
                processing_path.unlink(missing_ok=True)
        time.sleep(2)


if __name__ == "__main__":
    run()
