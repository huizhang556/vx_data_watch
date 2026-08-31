from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from app import backups
from app.security import decrypt_bytes


def test_sqlite_backup_is_encrypted_and_restorable(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    database = tmp_path / "source.db"
    connection = sqlite3.connect(database)
    connection.execute("create table sample (value text not null)")
    connection.execute("insert into sample values ('before-backup')")
    connection.commit()
    connection.close()
    settings = SimpleNamespace(database_url=f"sqlite:///{database}", data_dir=tmp_path)
    monkeypatch.setattr(backups, "get_settings", lambda: settings)

    archive = backups.create_backup()
    assert archive.suffix == ".vxbackup"
    assert archive.read_bytes().startswith(b"VX1")
    assert b"before-backup" in decrypt_bytes(archive.read_bytes())

    database.unlink()
    backups.restore_backup(archive)
    restored = sqlite3.connect(database)
    assert restored.execute("select value from sample").fetchone() == ("before-backup",)
    restored.close()


def test_postgres_backup_and_restore_use_safe_client_flags(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = SimpleNamespace(
        database_url="postgresql+psycopg://user:password@localhost:5432/vx_data",
        data_dir=tmp_path,
    )
    monkeypatch.setattr(backups, "get_settings", lambda: settings)
    calls: list[dict[str, object]] = []

    class Result:
        stdout = b"create table sample(value text);"

    def run(args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append({"args": args, **kwargs})
        return Result()

    monkeypatch.setattr(backups.subprocess, "run", run)
    archive = backups.create_backup()
    assert decrypt_bytes(archive.read_bytes()) == Result.stdout
    assert calls[0]["args"][:2] == ["pg_dump", "--no-owner"]
    assert calls[0]["args"][-2:] == ["--dbname", "postgresql://user@localhost:5432/vx_data"]
    assert calls[0]["env"]["PGPASSWORD"] == "password"  # type: ignore[index]

    backups.restore_backup(archive)
    assert calls[1]["args"][:3] == ["psql", "--set", "ON_ERROR_STOP=1"]
    assert calls[1]["input"] == Result.stdout
    assert calls[1]["env"]["PGPASSWORD"] == "password"  # type: ignore[index]
