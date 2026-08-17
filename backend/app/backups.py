from __future__ import annotations

import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from .config import get_settings
from .security import decrypt_bytes, encrypt_bytes


def _database_path() -> Path:
    url = get_settings().database_url
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise RuntimeError("备份仅支持 SQLite")
    return Path(url[len(prefix) :]).resolve()


def create_backup() -> Path:
    settings = get_settings()
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"vx-data-{timestamp}.vxbackup"
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
    database_path = _database_path()
    plaintext = decrypt_bytes(backup_path.read_bytes())
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
