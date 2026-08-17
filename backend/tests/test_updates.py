from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from app import updater, updates


def test_version_payload_only_offers_newer_semver(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        updates,
        "get_settings",
        lambda: SimpleNamespace(update_repository="litehub/vx-data-watch", updater_enabled=True),
    )
    payload = updates.version_payload(
        [
            {"version": "0.4.0"},
            {"version": "0.3.1"},
            {"version": "0.3.0"},
            {"version": "0.2.1"},
        ]
    )
    assert payload["current_version"] == "0.3.0"
    assert [row["version"] for row in payload["versions"]] == ["0.4.0", "0.3.1"]
    assert payload["update_supported"] is True
    with pytest.raises(ValueError, match="语义版本"):
        updates.version_key("latest")


def test_queue_rejects_parallel_update(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = SimpleNamespace(data_dir=tmp_path, update_repository="litehub/vx-data-watch")
    monkeypatch.setattr(updates, "get_settings", lambda: settings)
    request = updates.queue_update("0.3.1", "backup.vxbackup")
    assert request["version"] == "0.3.1"
    assert updates.read_update_status()["state"] == "queued"
    with pytest.raises(updates.UpdateBusyError):
        updates.queue_update("0.4.0", "backup-2.vxbackup")


def test_updater_pulls_replaces_and_persists_image(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    env_file = tmp_path / ".env"
    env_file.write_text("VX_PORT=8000\n# VX_IMAGE=old/image:tag\n", encoding="utf-8")
    settings = SimpleNamespace(
        data_dir=tmp_path,
        update_repository="litehub/vx-data-watch",
        update_project="vx-data-watch",
        update_service="app",
        update_env_file=env_file,
    )
    monkeypatch.setattr(updater, "get_settings", lambda: settings)
    monkeypatch.setattr(updates, "get_settings", lambda: settings)

    class FakeEngine:
        calls: list[tuple[object, ...]] = []

        def pull(self, repository: str, version: str) -> None:
            self.calls.append(("pull", repository, version))

        def replace_compose_service(
            self, project: str, service: str, repository: str, version: str
        ) -> None:
            self.calls.append(("replace", project, service, repository, version))

    engine = FakeEngine()
    updater.process_update(
        {"id": "request-1", "repository": "litehub/vx-data-watch", "version": "0.3.1"},
        engine=engine,  # type: ignore[arg-type]
    )
    assert engine.calls == [
        ("pull", "litehub/vx-data-watch", "0.3.1"),
        ("replace", "vx-data-watch", "app", "litehub/vx-data-watch", "0.3.1"),
    ]
    assert "VX_IMAGE=docker.io/litehub/vx-data-watch:0.3.1" in env_file.read_text()
    assert updates.read_update_status()["state"] == "success"


def test_updater_restores_env_when_replacement_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    env_file = tmp_path / ".env"
    original = "VX_IMAGE=docker.io/litehub/vx-data-watch:0.3.0\n"
    env_file.write_text(original, encoding="utf-8")
    settings = SimpleNamespace(
        data_dir=tmp_path,
        update_repository="litehub/vx-data-watch",
        update_project="vx-data-watch",
        update_service="app",
        update_env_file=env_file,
    )
    monkeypatch.setattr(updater, "get_settings", lambda: settings)
    monkeypatch.setattr(updates, "get_settings", lambda: settings)

    class FailingEngine:
        def pull(self, _repository: str, _version: str) -> None:
            pass

        def replace_compose_service(self, *_args: str) -> None:
            raise RuntimeError("health check failed")

    with pytest.raises(RuntimeError, match="health check failed"):
        updater.process_update(
            {"id": "request-2", "repository": "litehub/vx-data-watch", "version": "0.3.1"},
            engine=FailingEngine(),  # type: ignore[arg-type]
        )
    assert env_file.read_text(encoding="utf-8") == original
    assert updates.read_update_status()["state"] == "rolling_back"
