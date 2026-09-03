from __future__ import annotations

from fastapi.testclient import TestClient
from zipfile import ZipFile
from io import BytesIO

from .test_importer import CSV_SAMPLE


def upload_csv(
    client: TestClient, headers: dict[str, str], account_id: int, content: bytes, action: str
):
    return client.post(
        f"/api/imports/account-csv/{action}",
        headers=headers,
        data={"account_id": str(account_id), "data_end_date": "2026-08-16"},
        files={"file": ("视频号视频详情数据.csv", content, "text/csv")},
    )


def test_requires_csrf(client: TestClient, auth: dict[str, str]) -> None:
    response = client.post("/api/accounts", json={"name": "无 CSRF"})
    assert response.status_code == 403


def test_admin_can_create_user(client: TestClient, auth: dict[str, str]) -> None:
    response = client.post(
        "/api/users",
        headers=auth,
            json={"username": "viewer", "email": "viewer@example.com", "password": "viewer-pass-123", "role": "viewer"},
    )
    assert response.status_code == 201, response.text
    users = client.get("/api/users")
    assert users.status_code == 200
    assert any(row["username"] == "viewer" for row in users.json())


def test_menu_visibility_normalizes_hidden_parent_groups(client: TestClient, auth: dict[str, str]) -> None:
    payload = {
        "/users/accounts": False,
        "/users/local": False,
        "/ai-chat/config": False,
        "/ai-chat": False,
        "/analysis/dashboard": False,
        "/analysis/videos": False,
        "/analysis/imports": False,
        "/analysis/ai": False,
    }
    saved = client.put("/api/settings/menu-visibility", headers=auth, json=payload)
    assert saved.status_code == 200, saved.text
    values = saved.json()
    assert values["/users"] is False
    assert values["/ai-chat-menu"] is False
    assert values["/analysis"] is False
    unknown = client.put("/api/settings/menu-visibility", headers=auth, json={"/unknown": False})
    assert unknown.status_code == 422


def test_user_accounts_are_private_from_administrator(
    client: TestClient, auth: dict[str, str]
) -> None:
    from app.main import app

    # Use an isolated cookie jar so the shared admin fixture remains valid for
    # the tests that follow this one.
    with TestClient(app) as session:
        login = session.post(
            "/api/auth/login", json={"username": "viewer", "password": "viewer-pass-123"}
        )
        assert login.status_code == 200, login.text
        viewer_headers = {"X-CSRF-Token": login.json()["csrf_token"]}

        created = session.post(
            "/api/accounts",
            headers=viewer_headers,
            json={"name": "普通用户私有账号", "description": "仅本人可见"},
        )
        assert created.status_code == 201, created.text
        private_account_id = created.json()["id"]

        admin_login = session.post(
            "/api/auth/login", json={"username": "admin", "password": "secure-pass-123"}
        )
        assert admin_login.status_code == 200, admin_login.text

        listed = session.get("/api/accounts")
        assert listed.status_code == 200
        assert private_account_id not in {row["id"] for row in listed.json()}
        denied = session.get(
            f"/api/analytics/available-dates?account_id={private_account_id}"
        )
        assert denied.status_code == 404


def test_regular_user_can_update_own_profile_only(client: TestClient, auth: dict[str, str]) -> None:
    from app.main import app

    with TestClient(app) as session:
        login = session.post(
            "/api/auth/login", json={"username": "viewer", "password": "viewer-pass-123"}
        )
        assert login.status_code == 200, login.text
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        updated = session.put(
            "/api/auth/profile",
            headers=headers,
            json={
                "username": "viewer_self",
                "email": "viewer-self@example.com",
                "avatar": "data:image/png;base64,dGVzdA==",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["username"] == "viewer_self"
        assert updated.json()["avatar"].startswith("data:image/png")
        assert session.get("/api/users").status_code == 403

    # The administrator's user-management endpoint remains available to admins.
    admin_users = client.get("/api/users")
    assert admin_users.status_code == 200


def test_auth_settings_forms_update_independently(client: TestClient, auth: dict[str, str]) -> None:
    email_only = client.put(
        "/api/settings/auth", headers=auth, json={"registration_enabled": True}
    )
    assert email_only.status_code == 200, email_only.text
    assert email_only.json()["registration_enabled"] is True
    assert email_only.json()["captcha_enabled"] is False

    captcha_only = client.put(
        "/api/settings/auth",
        headers=auth,
        json={"captcha_enabled": True, "captcha_site_key": "site-key"},
    )
    assert captcha_only.status_code == 200, captcha_only.text
    saved = client.get("/api/settings/auth")
    assert saved.status_code == 200, saved.text
    assert saved.json()["registration_enabled"] is True
    assert saved.json()["captcha_enabled"] is True
    # Keep the shared test database usable for the following authentication tests.
    reset = client.put(
        "/api/settings/auth",
        headers=auth,
        json={"registration_enabled": False, "captcha_enabled": False},
    )
    assert reset.status_code == 200, reset.text


def test_download_cookies_are_saved_per_user(client: TestClient, auth: dict[str, str]) -> None:
    cookies = ".youtube.com\tTRUE\t/\tTRUE\t0\tYSC\ttest-token"
    response = client.put(
        "/api/download/settings",
        headers=auth,
        json={"cookies": cookies},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cookies_set"] is True
    assert response.json()["cookies"] == ""
    status = client.get("/api/download/cookies/status")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["valid"] is True


def test_completed_download_can_be_retrieved_as_archive(
    client: TestClient, auth: dict[str, str]
) -> None:
    from app.config import get_settings
    from app.database import SessionLocal
    from app.models import DownloadTask

    created = client.post(
        "/api/download/tasks", headers=auth, json={"urls": ["https://youtu.be/test-video"]}
    )
    assert created.status_code == 201, created.text
    task_id = created.json()[0]["id"]
    output_dir = get_settings().data_dir / f"download-test-{task_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "video.mp4").write_bytes(b"test-video")
    with SessionLocal() as db:
        task = db.get(DownloadTask, task_id)
        assert task is not None
        task.status = "completed"
        task.progress = 100
        task.output_path = str(output_dir)
        db.commit()

    response = client.get(f"/api/download/tasks/{task_id}/file")
    assert response.status_code == 200, response.text
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.namelist() == ["video.mp4"]
        assert archive.read("video.mp4") == b"test-video"


def test_admin_can_check_and_queue_system_update(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    from app import main
    from app.updates import update_paths

    async def versions(_repository: str, _registry: str = "docker.io") -> list[dict[str, str]]:
        return [
                {"version": "0.5.4", "published_at": "2026-09-04T00:00:00Z"},
                {"version": "0.5.3", "published_at": "2026-09-03T00:00:00Z"},
            {"version": "0.4.3", "published_at": "2026-08-28T00:00:00Z"},
            {"version": "0.4.2", "published_at": "2026-08-20T00:00:00Z"},
                {"version": "0.4.0", "published_at": "2026-08-19T00:00:00Z"},
            {"version": "0.3.4", "published_at": "2026-08-19T00:00:00Z"},
        ]

    monkeypatch.setattr(main, "fetch_registry_versions", versions)
    monkeypatch.setattr(main.settings, "updater_enabled", True)
    for path in update_paths():
        path.unlink(missing_ok=True)

    checked = client.get("/api/system/versions")
    assert checked.status_code == 200, checked.text
    assert checked.json()["current_version"] == "0.5.4"
    assert [row["version"] for row in checked.json()["versions"]] == ["0.5.3", "0.4.3", "0.4.2", "0.4.0", "0.3.4"]

    queued = client.post(
        "/api/system/update", headers=auth, json={"version": "0.4.0"}
    )
    assert queued.status_code == 202, queued.text
    assert queued.json()["state"] == "queued"
    assert queued.json()["backup_filename"].endswith(".vxbackup")
    assert client.get("/api/system/update-status").json()["target_version"] == "0.4.0"
    for path in update_paths():
        path.unlink(missing_ok=True)


def test_csv_preview_commit_revision_and_analytics(
    client: TestClient,
    auth: dict[str, str],
    account_id: int,
) -> None:
    preview = upload_csv(client, auth, account_id, CSV_SAMPLE, "preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"] == {"new": 2, "update": 0, "duplicate": 0}

    committed = upload_csv(client, auth, account_id, CSV_SAMPLE, "commit")
    assert committed.status_code == 201, committed.text
    assert committed.json()["summary"]["new"] == 2

    duplicate = upload_csv(client, auth, account_id, CSV_SAMPLE, "commit")
    assert duplicate.status_code == 201
    assert duplicate.json()["summary"]["duplicate"] == 2

    revised_content = CSV_SAMPLE.replace(b"1200", b"1210")
    revised = upload_csv(client, auth, account_id, revised_content, "commit")
    assert revised.status_code == 201
    assert revised.json()["summary"] == {"new": 0, "update": 1, "duplicate": 1}

    trend = client.get(
        f"/api/analytics/range?account_id={account_id}&start_date=2026-08-15&end_date=2026-08-16"
    )
    assert trend.status_code == 200
    assert trend.json()["days_with_data"] == 2
    assert trend.json()["totals"]["plays"] == 2010
    assert trend.json()["totals"]["favorites"] is None
    single = client.get(
        f"/api/analytics/range?account_id={account_id}&start_date=2026-08-16&end_date=2026-08-16"
    )
    assert single.status_code == 200
    assert single.json()["previous_totals"]["plays"] == 800


def test_video_commit_reconciliation_and_backup(
    client: TestClient,
    auth: dict[str, str],
    account_id: int,
) -> None:
    response = client.post(
        "/api/imports/video-metrics/commit",
        headers=auth,
        json={
            "account_id": account_id,
            "filename": "截图确认",
            "rows": [
                {
                    "title": "视频 A",
                    "published_at": "2026-08-14T21:49:00",
                    "metric_date": "2026-08-16",
                    "plays": 600,
                    "likes": 30,
                    "comments": 8,
                    "shares": 15,
                },
                {
                    "title": "视频 B",
                    "published_at": "2026-08-12T23:47:00",
                    "metric_date": "2026-08-16",
                    "plays": 250,
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    daily = client.get(f"/api/analytics/day?account_id={account_id}&metric_date=2026-08-16")
    assert daily.status_code == 200
    assert daily.json()["reconciliation"]["video_total"] == 850
    assert daily.json()["videos"][0]["plays"] == 600

    ranged = client.get(
        f"/api/analytics/videos?account_id={account_id}&start_date=2026-08-15&end_date=2026-08-16"
    )
    assert ranged.status_code == 200, ranged.text
    assert ranged.json()["videos"][0]["plays"] == 600
    assert ranged.json()["reconciliation"]["video_total"] == 850

    backup = client.post("/api/backups", headers=auth)
    assert backup.status_code == 201, backup.text
    assert backup.json()["filename"].endswith(".vxbackup")


def test_spa_refresh_does_not_mask_missing_api(client: TestClient) -> None:
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert 'id="root"' in dashboard.text

    missing_api = client.get("/api/not-a-route")
    assert missing_api.status_code == 404


def test_logout_is_idempotent_and_clears_session() -> None:
    from app.main import app

    with TestClient(app) as session_client:
        login = session_client.post(
            "/api/auth/login", json={"username": "admin", "password": "secure-pass-123"}
        )
        assert login.status_code == 200

        logout = session_client.post("/api/auth/logout")
        assert logout.status_code == 204
        assert "vx_session" not in session_client.cookies
        assert session_client.get("/api/auth/me").status_code == 401
        assert session_client.post("/api/auth/logout").status_code == 204


def test_secure_cookie_does_not_break_plain_http_session() -> None:
    from app import main

    previous = main.settings.cookie_secure
    main.settings.cookie_secure = True
    try:
        with TestClient(main.app, base_url="http://testserver") as session_client:
            login = session_client.post(
                "/api/auth/login", json={"username": "admin", "password": "secure-pass-123"}
            )
            assert login.status_code == 200
            assert "Secure" not in login.headers["set-cookie"]
            assert session_client.get("/api/auth/me").status_code == 200
            assert session_client.post("/api/auth/logout").status_code == 204
    finally:
        main.settings.cookie_secure = previous


def test_ai_analysis_returns_report_but_history_does_not_store_body(
    client: TestClient,
    auth: dict[str, str],
    account_id: int,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    from app import main

    calls = 0

    async def report(_config, _snapshot) -> str:  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return "# 分析结果\n\n- 建议一"

    async def provider_test(**_kwargs) -> str:  # type: ignore[no-untyped-def]
        return "连接成功"

    monkeypatch.setattr(main, "test_provider_values", provider_test)
    configured = client.post(
        "/api/ai/provider/test-and-save",
        headers=auth,
        json={
            "account_id": account_id,
            "name": "测试 AI",
            "base_url": "https://ai.example.test/v1",
            "model": "test-model",
            "protocol": "chat_completions",
            "api_key": "secret-test-key",
            "timeout_seconds": 30,
        },
    )
    assert configured.status_code == 200, configured.text
    monkeypatch.setattr(main, "call_provider", report)
    response = client.post(
        "/api/ai/analyze",
        headers=auth,
        json={"account_id": account_id, "start_date": "2026-08-15", "end_date": "2026-08-16"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["report_text"].startswith("# 分析结果")
    assert response.json()["snapshot"]["totals"]["plays"] == 2010

    history = client.get(f"/api/ai/reports?account_id={account_id}")
    assert history.status_code == 200
    assert history.json()
    assert "report_text" not in history.json()[0]
    history_id = response.json()["id"]
    history_count = len(history.json())

    viewed = client.post(f"/api/ai/reports/{history_id}/analyze", headers=auth)
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["id"] == history_id
    assert viewed.json()["report_text"].startswith("# 分析结果")
    assert calls == 1
    assert len(client.get(f"/api/ai/reports?account_id={account_id}").json()) == history_count

    deleted = client.delete(f"/api/ai/reports/{history_id}", headers=auth)
    assert deleted.status_code == 204
    ids = [row["id"] for row in client.get(f"/api/ai/reports?account_id={account_id}").json()]
    assert history_id not in ids
    assert client.delete(f"/api/ai/reports/{history_id}", headers=auth).status_code == 404
