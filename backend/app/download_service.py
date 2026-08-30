from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
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
_controls: dict[int, dict[str, threading.Event]] = {}


class DownloadControl(Exception):
    def __init__(self, status: str) -> None:
        self.status = status


def _settings(db: Session, user_id: int | None = None) -> dict[str, Any]:
    key = f"download:{user_id}" if user_id is not None else "download"
    row = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if not row and user_id is not None:
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


def _check_proxy(proxy_url: str) -> None:
    """Perform a short connectivity check before a download when requested."""
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
        with opener.open("https://www.youtube.com/generate_204", timeout=10) as response:
            if response.status >= 400:
                raise OSError(f"HTTP {response.status}")
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise ValueError(f"代理连接失败：{exc}") from exc


def start_task(task_id: int) -> bool:
    with _workers_lock:
        if task_id in _workers and _workers[task_id].is_alive():
            return False
        worker = threading.Thread(target=_run_task, args=(task_id,), daemon=True)
        _workers[task_id] = worker
        _controls[task_id] = {"pause": threading.Event(), "cancel": threading.Event()}
        worker.start()
    return True


def _run_task(task_id: int) -> None:
    from .database import SessionLocal

    db = SessionLocal()
    cookie_path: Path | None = None
    task: DownloadTask | None = None
    try:
        task = db.get(DownloadTask, task_id)
        if not task:
            return
        options = _settings(db, task.user_id)
        control = _controls.setdefault(task_id, {"pause": threading.Event(), "cancel": threading.Event()})
        relative_dir = str(options.get("output_dir") or "downloads").replace("\\", "/").strip("/")
        output_dir = (get_settings().data_dir / relative_dir).resolve()
        data_root = get_settings().data_dir.resolve()
        if data_root not in output_dir.parents and output_dir != data_root:
            raise ValueError("下载目录必须位于数据目录内")
        output_dir.mkdir(parents=True, exist_ok=True)
        cookie_text = str(options.get("cookies") or "")
        if options.get("cookies_enabled") and cookie_text:
            cookie_path = output_dir / f".cookies-{task_id}.txt"
            cookie_path.write_text(cookie_text, encoding="utf-8")
        proxy_url = str(options.get("proxy_url") or "").strip()
        if options.get("proxy_enabled") and options.get("proxy_auto_check") and proxy_url:
            _check_proxy(proxy_url)
        task.status = "downloading"
        task.error = None
        db.commit()

        def progress(data: dict[str, Any]) -> None:
            if control["cancel"].is_set():
                raise DownloadControl("cancelled")
            if control["pause"].is_set():
                raise DownloadControl("paused")
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
        if options.get("proxy_enabled") and options.get("proxy_url"):
            ydl_options["proxy"] = str(options["proxy_url"])
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
        size = info.get("filesize") or info.get("filesize_approx")
        if isinstance(size, (int, float)) and size > 0:
            units = ("B", "KB", "MB", "GB", "TB")
            value = float(size)
            unit = units[0]
            for unit in units:
                if value < 1024 or unit == units[-1]:
                    break
                value /= 1024
            task.estimated_size = f"{value:.1f} {unit}"
        task.status = "completed"
        task.progress = 100
        task.output_path = str(output_dir)
        db.commit()
    except DownloadControl as exc:
        task = db.get(DownloadTask, task_id)
        if task:
            task.status = exc.status
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
        with _workers_lock:
            _workers.pop(task_id, None)
            _controls.pop(task_id, None)

def pause_task(task_id: int) -> bool:
    control = _controls.get(task_id)
    if not control:
        return False
    control["pause"].set()
    return True

def cancel_task(task_id: int) -> bool:
    control = _controls.get(task_id)
    if not control:
        return False
    control["cancel"].set()
    return True
