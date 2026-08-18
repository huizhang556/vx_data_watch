from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import get_settings
from .docker_engine import DockerEngine
from .updates import (
    SEMVER_PATTERN,
    prepare_update_dir_for_app,
    update_paths,
    write_json_atomic,
)


def _status(request: dict[str, Any], state: str, message: str, **extra: Any) -> None:
    _, _, status_path = update_paths()
    write_json_atomic(
        status_path,
        {
            "id": request.get("id"),
            "state": state,
            "target_version": request.get("version"),
            "message": message,
            "updated_at": datetime.now(UTC).isoformat(),
            **extra,
        },
    )


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


def process_update(request: dict[str, Any], engine: DockerEngine | None = None) -> None:
    settings = get_settings()
    version = request.get("version")
    repository = request.get("repository")
    if not isinstance(version, str) or not SEMVER_PATTERN.fullmatch(version):
        raise ValueError("更新版本号无效")
    if repository != settings.update_repository:
        raise ValueError("更新镜像仓库不在允许列表中")
    docker = engine or DockerEngine()
    _status(request, "pulling", "正在拉取目标镜像")
    docker.pull(repository, version)
    env_existed = settings.update_env_file.exists()
    previous_env = (
        settings.update_env_file.read_text(encoding="utf-8") if env_existed else ""
    )
    _persist_image(settings.update_env_file, f"docker.io/{repository}:{version}")
    _status(request, "restarting", "正在替换并重启应用")
    try:
        docker.replace_compose_service(
            settings.update_project, settings.update_service, repository, version
        )
    except Exception:
        _status(request, "rolling_back", "更新失败，正在恢复原版本")
        if env_existed:
            settings.update_env_file.write_text(previous_env, encoding="utf-8")
        else:
            settings.update_env_file.unlink(missing_ok=True)
        raise
    _status(request, "success", "更新完成", current_version=version)


def run() -> None:
    prepare_update_dir_for_app()
    request_path, processing_path, _ = update_paths()
    while True:
        if request_path.exists() and not processing_path.exists():
            request: dict[str, Any] = {}
            try:
                request_path.replace(processing_path)
                request = json.loads(processing_path.read_text(encoding="utf-8"))
                process_update(request)
            except Exception as exc:
                _status(request, "failed", f"更新失败：{exc}")
            finally:
                processing_path.unlink(missing_ok=True)
        time.sleep(2)


if __name__ == "__main__":
    run()
