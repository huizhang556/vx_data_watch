from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL

from .config import get_settings
from .models import AppSetting, DownloadTask
from .security import decrypt_secret

_workers: dict[int, threading.Thread] = {}
_workers_lock = threading.Lock()


def _settings(db: Session) -> dict[str, Any]:
    row = db.scalar(select(AppSetting).where(AppSetting.key == "download"))
    if not row:
        return {}
    try:
        value = json.loads(decrypt_secret(row.value))
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}


def _format_selector(options: dict[str, Any]) -> str:
    quality = options.get("quality", "1080")
    height = "best" if quality == "best" else f"[height<={quality}]"
    download_type = options.get("download_type", "video_audio")
    if download_type == "audio":
        return "bestaudio/best"
    if download_type == "video":
        return f"bestvideo{height}/best"
    return f"bestvideo{height}+bestaudio/best"


def start_task(task_id: int) -> bool:
    with _workers_lock:
        if task_id in _workers and _workers[task_id].is_alive():
            return False
        worker = threading.Thread(target=_run_task, args=(task_id,), daemon=True)
        _workers[task_id] = worker
        worker.start()
    return True


def _run_task(task_id: int) -> None:
    from .database import SessionLocal

    db = SessionLocal()
    cookie_path: Path | None = None
    try:
        task = db.get(DownloadTask, task_id)
        if not task:
            return
        options = _settings(db)
        output_dir = get_settings().data_dir / "downloads"
        output_dir.mkdir(parents=True, exist_ok=True)
        cookie_text = str(options.get("cookies") or "")
        if options.get("cookies_enabled") and cookie_text:
            cookie_path = output_dir / f".cookies-{task_id}.txt"
            cookie_path.write_text(cookie_text, encoding="utf-8")
        task.status = "downloading"
        task.error = None
        db.commit()

        def progress(data: dict[str, Any]) -> None:
            if data.get("status") == "downloading":
                task.progress = float(data.get("_percent_str", "0%").strip(" %") or 0)
                db.commit()
            elif data.get("status") == "finished":
                task.progress = 100
                db.commit()

        ydl_options: dict[str, Any] = {
            "format": _format_selector(options),
            "outtmpl": str(output_dir / "%(title)s [%(id)s].%(ext)s"),
            "noplaylist": True,
            "progress_hooks": [progress],
            "writethumbnail": bool(options.get("save_thumbnail", True)),
            "postprocessors": [],
            "quiet": True,
        }
        if cookie_path:
            ydl_options["cookiefile"] = str(cookie_path)
        if options.get("transcode_enabled"):
            ydl_options["postprocessors"].append({
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            })
        with YoutubeDL(ydl_options) as downloader:
            info = downloader.extract_info(task.url, download=True)
        task.title = str(info.get("title") or task.title or "")[:500]
        task.duration = str(info.get("duration_string") or "")[:30]
        task.status = "completed"
        task.progress = 100
        task.output_path = str(output_dir)
        db.commit()
    except Exception as exc:
        task = db.get(DownloadTask, task_id)
        if task:
            task.status = "failed"
            task.error = str(exc)[-2000:]
            db.commit()
    finally:
        if cookie_path:
            cookie_path.unlink(missing_ok=True)
        db.close()