from __future__ import annotations

from fastapi.testclient import TestClient

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
        json={"username": "viewer", "password": "viewer-pass-123", "role": "viewer"},
    )
    assert response.status_code == 201, response.text
    users = client.get("/api/users")
    assert users.status_code == 200
    assert any(row["username"] == "viewer" for row in users.json())


def test_admin_can_check_and_queue_system_update(
    client: TestClient,
    auth: dict[str, str],
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    from app import main
    from app.updates import update_paths

    async def versions(_repository: str) -> list[dict[str, str]]:
        return [
            {"version": "0.4.0", "published_at": "2026-08-20T00:00:00Z"},
            {"version": "0.3.4", "published_at": "2026-08-19T00:00:00Z"},
        ]

    monkeypatch.setattr(main, "fetch_registry_versions", versions)
    monkeypatch.setattr(main.settings, "updater_enabled", True)
    for path in update_paths():
        path.unlink(missing_ok=True)

    checked = client.get("/api/system/versions")
    assert checked.status_code == 200, checked.text
    assert checked.json()["current_version"] == "0.3.7"
    assert [row["version"] for row in checked.json()["versions"]] == ["0.4.0", "0.3.4"]

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
