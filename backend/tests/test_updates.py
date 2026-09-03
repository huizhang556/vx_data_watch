from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx
from app import updater, updates
from app.docker_engine import DockerEngine, DockerEngineError


def test_docker_pull_retries_transient_engine_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    engine = DockerEngine()
    calls = 0

    def request(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls < 3:
            raise DockerEngineError("temporary network failure")
        return "{}"

    monkeypatch.setattr(engine, "_request", request)
    monkeypatch.setattr("app.docker_engine.time.sleep", lambda _seconds: None)
    engine.pull("litehub/vx-data-watch", "0.5.3")
    assert calls == 3


def test_version_payload_offers_all_other_semver_versions(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        updates,
        "get_settings",
        lambda: SimpleNamespace(update_repository="litehub/vx-data-watch", updater_enabled=True),
    )
    payload = updates.version_payload(
        [
            {"version": "0.5.3"},
            {"version": "0.5.1"},
            {"version": "0.4.3"},
            {"version": "0.4.2"},
            {"version": "0.3.4"},
            {"version": "0.3.3"},
            {"version": "0.3.2"},
            {"version": "0.3.0"},
            {"version": "0.2.1"},
        ]
    )
    assert payload["current_version"] == "0.5.4"
    assert [row["version"] for row in payload["versions"]] == ["0.5.3", "0.5.1", "0.4.3", "0.4.2", "0.3.4", "0.3.3", "0.3.2", "0.3.0", "0.2.1"]
    assert payload["update_supported"] is True
    with pytest.raises(ValueError, match="语义版本"):
        updates.version_key("latest")


def test_acr_registry_token_authentication(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.calls: list[tuple[str, str]] = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params=None, headers=None):  # type: ignore[no-untyped-def]
                self.calls.append((url, (headers or {}).get("Authorization", "")))
                if "tags/list" in url and not headers:
                    return httpx.Response(
                        401,
                        headers={
                            "WWW-Authenticate":
                            'Bearer realm="https://auth.example.test/token",service="registry.example",scope="repository:team/app:pull"'
                        },
                        request=httpx.Request("GET", url),
                    )
                if "auth.example.test" in url:
                    return httpx.Response(200, json={"token": "test-token"}, request=httpx.Request("GET", url))
                return httpx.Response(200, json={"tags": ["0.5.4", "0.5.3", "latest"]}, request=httpx.Request("GET", url))

        fake = FakeClient()
        monkeypatch.setattr(updates.httpx, "AsyncClient", lambda *args, **kwargs: fake)
        result = await updates.fetch_registry_versions(
            "team/app", "crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com"
        )
        assert [row["version"] for row in result] == ["0.5.4", "0.5.3"]
        assert any(auth == "Bearer test-token" for _, auth in fake.calls)

    asyncio.run(run())


def test_registry_version_cache_is_scoped_by_registry(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def run() -> None:
        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params=None, headers=None):  # type: ignore[no-untyped-def]
                if "hub.docker.com" in url:
                    return httpx.Response(200, json={"results": [{"name": "0.4.0"}]}, request=httpx.Request("GET", url))
                if "registry-1.docker.io" in url:
                    return httpx.Response(200, json={"tags": ["0.4.0"]}, request=httpx.Request("GET", url))
                return httpx.Response(200, json={"tags": ["0.5.4", "0.5.3"]}, request=httpx.Request("GET", url))

        monkeypatch.setattr(updates.httpx, "AsyncClient", FakeClient)
        updates._version_cache.clear()
        docker = await updates.fetch_registry_versions("litehub/vx-data-watch", "docker.io")
        acr = await updates.fetch_registry_versions(
            "zhang_spaces/vx-data-watch", "crpi-k1zyo7p3ez2ovrc3.cn-chengdu.personal.cr.aliyuncs.com"
        )
        assert [row["version"] for row in docker] == ["0.4.0"]
        assert [row["version"] for row in acr] == ["0.5.4", "0.5.3"]

    asyncio.run(run())


def test_queue_rejects_parallel_update(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = SimpleNamespace(data_dir=tmp_path, update_repository="litehub/vx-data-watch")
    monkeypatch.setattr(updates, "get_settings", lambda: settings)
    request = updates.queue_update("0.3.2", "backup.vxbackup")
    assert request["version"] == "0.3.2"
    assert updates.read_update_status()["state"] == "queued"
    with pytest.raises(updates.UpdateBusyError):
        updates.queue_update("0.4.0", "backup-2.vxbackup")


def test_prepare_update_dir_repairs_root_owned_directory(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(updates.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(
        updates.os,
        "chown",
        lambda path, uid, gid: calls.append((uid, gid)),
        raising=False,
    )
    directory = updates.prepare_update_dir_for_app(tmp_path / "updates")
    assert directory.is_dir()
    assert calls == [(10001, 10001)]


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

        def tag(self, source: str, repository: str, tag: str) -> None:
            self.calls.append(("tag", source, repository, tag))

        def replace_compose_service(
            self, project: str, service: str, repository: str, version: str
        ) -> None:
            self.calls.append(("replace", project, service, repository, version))

    engine = FakeEngine()
    updater.process_update(
        {"id": "request-1", "repository": "litehub/vx-data-watch", "version": "0.3.2"},
        engine=engine,  # type: ignore[arg-type]
    )
    assert engine.calls == [
        ("pull", "litehub/vx-data-watch", "0.3.2"),
        ("tag", "litehub/vx-data-watch:0.3.2", "docker.io/litehub/vx-data-watch", "latest"),
        ("replace", "vx-data-watch", "app", "docker.io/litehub/vx-data-watch", "latest"),
    ]
    assert "VX_IMAGE=docker.io/litehub/vx-data-watch:latest" in env_file.read_text()
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

        def tag(self, _source: str, _repository: str, _tag: str) -> None:
            pass

        def replace_compose_service(self, *_args: str) -> None:
            raise RuntimeError("health check failed")

    with pytest.raises(RuntimeError, match="health check failed"):
        updater.process_update(
            {"id": "request-2", "repository": "litehub/vx-data-watch", "version": "0.3.2"},
            engine=FailingEngine(),  # type: ignore[arg-type]
        )
    assert env_file.read_text(encoding="utf-8") == original
    assert updates.read_update_status()["state"] == "rolling_back"
