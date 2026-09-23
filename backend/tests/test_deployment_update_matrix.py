from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import updater, updates


@pytest.mark.parametrize("deployment_method", ["script", "compose", "source"])
def test_update_request_preserves_deployment_metadata_and_actual_env_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deployment_method: str
) -> None:
    """Every deployment mode must queue against its configured project env file.

    This deliberately uses a non-standard temporary directory so a regression to
    /opt/vx-data-watch or the process working directory is caught.
    """
    env_file = tmp_path / "deployment" / ".env"
    env_file.parent.mkdir()
    env_file.write_text(
        "VX_IMAGE=docker.io/litehub/vx-data-watch:latest\n",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        data_dir=tmp_path / "data",
        update_repository="litehub/vx-data-watch",
        update_registry="docker.io",
        update_env_file=env_file,
        update_project="custom-project",
        update_service="app",
        deployment_method=deployment_method,
        updater_enabled=deployment_method != "source",
    )
    monkeypatch.setattr(updates, "get_settings", lambda: settings)

    request = updates.queue_update("0.5.8", "rollback.vxbackup", digest="sha256:" + "a" * 64)

    assert request["deployment_method"] == deployment_method
    assert request["image"] == "docker.io/litehub/vx-data-watch:latest"
    assert json.loads((settings.data_dir / "updates" / "request.json").read_text(encoding="utf-8"))["deployment_method"] == deployment_method


def test_source_config_migration_does_not_touch_docker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = SimpleNamespace(
        data_dir=tmp_path,
        deployment_method="source",
        update_env_file=tmp_path / ".env",
        update_project="custom-source-project",
        update_service="app",
    )
    monkeypatch.setattr(updater, "get_settings", lambda: settings)
    monkeypatch.setattr(updater, "update_paths", lambda: (tmp_path / "request.json", tmp_path / "processing.json", tmp_path / "status.json"))
    monkeypatch.setattr(updater, "update_history_dir", lambda: tmp_path / "history")

    class FailingDocker:
        def __getattr__(self, name: str):
            raise AssertionError(f"source deployment unexpectedly called Docker: {name}")

    updater.process_config_migration(
        {"id": "source-migration", "deployment_method": "source"},
        engine=FailingDocker(),  # type: ignore[arg-type]
    )
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "success"


@pytest.mark.parametrize("deployment_method", ["script", "compose"])
def test_container_deployment_config_migration_restarts_app_and_updater(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deployment_method: str
) -> None:
    settings = SimpleNamespace(
        data_dir=tmp_path,
        deployment_method=deployment_method,
        update_registry="docker.io",
        update_repository="litehub/vx-data-watch",
        update_env_file=tmp_path / "deployment" / ".env",
        update_project="custom-project",
        update_service="app",
    )
    settings.update_env_file.parent.mkdir()
    settings.update_env_file.write_text("VX_IMAGE=docker.io/litehub/vx-data-watch:latest\n", encoding="utf-8")
    monkeypatch.setattr(updater, "get_settings", lambda: settings)
    monkeypatch.setattr(updater, "update_paths", lambda: (tmp_path / "request.json", tmp_path / "processing.json", tmp_path / "status.json"))
    monkeypatch.setattr(updater, "update_history_dir", lambda: tmp_path / "history")

    class Engine:
        calls: list[tuple[str, ...]] = []

        def replace_compose_service(self, project: str, service: str, repository: str, tag: str) -> None:
            self.calls.append(("replace", project, service, repository, tag))

        def replace_running_companion(self, project: str, service: str, repository: str, tag: str) -> str:
            self.calls.append(("companion", project, service, repository, tag))
            return "old-updater"

        def remove(self, container: str, force: bool = False) -> None:
            self.calls.append(("remove", container, str(force)))

    engine = Engine()
    updater.process_config_migration(
        {"id": f"{deployment_method}-migration", "deployment_method": deployment_method},
        engine=engine,  # type: ignore[arg-type]
    )
    assert engine.calls == [
        ("replace", "custom-project", "app", "docker.io/litehub/vx-data-watch", "latest"),
        ("companion", "custom-project", "updater", "docker.io/litehub/vx-data-watch", "latest"),
        ("remove", "old-updater", "True"),
    ]

