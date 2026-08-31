from __future__ import annotations

import os
import sqlite3
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import URL, make_url

from .config import get_settings
from .security import decrypt_bytes, encrypt_bytes


def _database_path() -> Path:
    url = get_settings().database_url
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise RuntimeError("备份仅支持 SQLite")
    return Path(url[len(prefix) :]).resolve()


def _is_postgres() -> bool:
    return get_settings().database_url.startswith(("postgresql://", "postgresql+"))


def _postgres_url() -> str:
    url = get_settings().database_url
    parsed = make_url(url)
    if parsed.drivername.startswith("postgresql+"):
        parsed = parsed.set(drivername="postgresql")
    return parsed.render_as_string(hide_password=False)


def _postgres_command() -> tuple[str, dict[str, str]]:
    """Return a password-free connection URL and a private client environment."""
    parsed = make_url(get_settings().database_url)
    password = parsed.password or ""
    drivername = "postgresql" if parsed.drivername.startswith("postgresql+") else parsed.drivername
    safe_url = URL.create(
        drivername=drivername,
        username=parsed.username,
        host=parsed.host,
        port=parsed.port,
        database=parsed.database,
        query=parsed.query,
    ).render_as_string(hide_password=False)
    environment = os.environ.copy()
    if password:
        environment["PGPASSWORD"] = password
    return safe_url, environment


def create_backup() -> Path:
    settings = get_settings()
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"vx-data-{timestamp}.vxbackup"
    if _is_postgres():
        try:
            postgres_url, environment = _postgres_command()
            result = subprocess.run(
                ["pg_dump", "--no-owner", "--no-privileges", "--dbname", postgres_url],
                check=True,
                capture_output=True,
                env=environment,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("未安装 PostgreSQL 客户端工具 pg_dump") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"PostgreSQL 备份失败：{detail or 'pg_dump 返回错误'}") from exc
        target.write_bytes(encrypt_bytes(result.stdout))
        return target

    source_path = _database_path()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        source = sqlite3.connect(source_path)
        destination = sqlite3.connect(temp_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        check = sqlite3.connect(temp_path)
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise RuntimeError("备份完整性检查失败")
        finally:
            check.close()
        target.write_bytes(encrypt_bytes(temp_path.read_bytes()))
    finally:
        temp_path.unlink(missing_ok=True)
    return target


def restore_backup(backup_path: Path) -> None:
    plaintext = decrypt_bytes(backup_path.read_bytes())
    if _is_postgres():
        try:
            postgres_url, environment = _postgres_command()
            subprocess.run(
                ["psql", "--set", "ON_ERROR_STOP=1", "--dbname", postgres_url],
                input=plaintext,
                check=True,
                capture_output=True,
                env=environment,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("未安装 PostgreSQL 客户端工具 psql") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"PostgreSQL 恢复失败：{detail or 'psql 返回错误'}") from exc
        return

    database_path = _database_path()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp:
        temp.write(plaintext)
        temp_path = Path(temp.name)
    try:
        check = sqlite3.connect(temp_path)
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise RuntimeError("备份文件完整性检查失败")
        finally:
            check.close()
        database_path.parent.mkdir(parents=True, exist_ok=True)
        Path(str(database_path) + "-wal").unlink(missing_ok=True)
        Path(str(database_path) + "-shm").unlink(missing_ok=True)
        temp_path.replace(database_path)
    finally:
        temp_path.unlink(missing_ok=True)
