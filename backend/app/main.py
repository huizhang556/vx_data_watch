from __future__ import annotations

import gc
import base64
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from fastapi.responses import Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .ai_service import (
    SYSTEM_PROMPT,
    build_prompt,
    call_provider,
    list_provider_models,
    test_provider,
    test_provider_values,
    stream_chat_provider,
)
from .analytics import date_summary, range_has_complete_data, range_summary, range_video_summary
from .audit import write_audit
from .auth_service import auth_settings, consume_code, email_user, normalize_email, require_captcha, save_auth_settings, send_code, test_smtp_connection
from .backups import create_backup
from .config import get_settings
from .database import SessionLocal, get_db, init_db
from .download_service import cancel_task, pause_task, start_task
from .deps import (
    CsrfUser,
    CurrentUser,
    require_admin,
    require_csrf_admin,
    require_csrf_editor,
)
from .importers import (
    ImportValidationError,
    file_sha256,
    parse_account_csv,
    parse_video_sheet,
    video_identity,
)
from .models import (
    AIAnalysisReport,
    AIProviderConfig,
    AIQueryHistory,
    AIQuickConfig,
    AIChatCategory,
    AIChatSession,
    AIChatMessage,
    AIChatAttachment,
    UsageCounter,
    AuditLog,
    AppSetting,
    ChannelsAccount,
    DailyAccountMetric,
    DailyAccountMetricRevision,
    DailyVideoMetric,
    DownloadTask,
    ImportBatch,
    ImportRow,
    ImportStatus,
    ImportType,
    LoginSession,
    Role,
    User,
    Video,
)
from .ocr import OCRUnavailableError, deduplicate_candidates, extract_screenshot_candidates
from .schemas import (
    AccountCreate,
    AuthSettingsUpdate,
    SMTPTestRequest,
    AIAnalyzeRequest,
    AIProviderDraft,
    AIProviderInput,
    AIProviderSelect,
    AIQuickConfigInput,
    AIChatCategoryInput,
    AIChatSessionInput,
    AIChatSessionUpdate,
    AIChatMessageInput,
    AIChatMessageUpdate,
    LoginRequest,
    PasswordChange,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterCodeRequest,
    RegisterRequest,
    SetupRequest,
    SystemRegistryUpdate,
    SystemUpdateRequest,
    UserCreate,
    UserAdminUpdate,
    UsernameChange,
    VideoMetricCommit,
    DownloadCookieTest,
    DownloadProxyTest,
    DownloadSettings,
    DownloadTaskCreate,
)
from .security import (
    decrypt_secret,
    encrypt_secret,
    hash_password,
    new_token,
    session_expiry,
    token_hash,
    verify_password,
)
from .updates import (
    ALLOWED_REGISTRIES,
    REGISTRY_REPOSITORIES,
    UpdateBusyError,
    UpdateRegistryError,
    fetch_registry_versions,
    queue_update,
    read_update_status,
    save_update_registry,
    version_key,
    version_payload,
)

settings = get_settings()
_login_attempts: dict[str, list[float]] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; connect-src 'self' https://challenges.cloudflare.com; font-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; frame-src https://challenges.cloudflare.com"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _secure_cookie(request: Request) -> bool:
    """Only mark cookies Secure when the browser connection is HTTPS.

    The app is commonly behind a TLS-terminating reverse proxy. Respect its
    forwarded protocol, while avoiding an unusable Secure cookie when an
    administrator accidentally enables VX_COOKIE_SECURE on plain HTTP.
    """
    if not settings.cookie_secure:
        return False
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return forwarded == "https" or request.url.scheme == "https"


def _set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        "vx_session",
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )


def _create_session(db: Session, user: User, request: Request) -> tuple[str, LoginSession]:
    raw_token = new_token()
    login_session = LoginSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        csrf_token=new_token(24),
        expires_at=session_expiry(),
        user_agent=(request.headers.get("user-agent") or "")[:300],
    )
    db.add(login_session)
    return raw_token, login_session


def _user_payload(user: User, csrf_token: str | None = None) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role.value,
        "level": user.level,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "avatar": user.avatar or "default",
        "csrf_token": csrf_token,
    }


def _read_upload(file: UploadFile) -> bytes:
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb} MB")
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    return content


def _get_account(db: Session, account_id: int, user: User | None = None) -> ChannelsAccount:
    account = db.get(ChannelsAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="视频号账号不存在")
    if user is not None:
        # Administrator-owned accounts are global (user_id is NULL), while
        # accounts created by regular users remain private to that user.
        if user.role == Role.admin and account.user_id is not None:
            raise HTTPException(status_code=404, detail="视频号账号不存在")
        if user.role != Role.admin and account.user_id != user.id:
            raise HTTPException(status_code=404, detail="视频号账号不存在")
    return account


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/api/system/database-capabilities")
def database_capabilities(user: Annotated[User, Depends(require_admin)]) -> dict[str, Any]:
    """Expose the database backends reserved by the deployment, without credentials."""
    url = get_settings().database_url
    scheme = url.split(":", 1)[0]
    return {
        "current_backend": "postgresql" if scheme.startswith("postgres") else "sqlite" if scheme == "sqlite" else scheme,
        "supported_backends": ["sqlite", "postgresql"],
        "migration_supported": True,
        "migration_status": "not_started",
    }


DOWNLOAD_SETTINGS_KEY = "download"
DOWNLOAD_DEFAULTS = DownloadSettings().model_dump()


def _download_settings(db: Session, user_id: int | None = None) -> dict[str, Any]:
    key = f"{DOWNLOAD_SETTINGS_KEY}:{user_id}" if user_id is not None else DOWNLOAD_SETTINGS_KEY
    row = db.scalar(select(AppSetting).where(AppSetting.key == key))
    if not row and user_id is not None:
        row = db.scalar(select(AppSetting).where(AppSetting.key == DOWNLOAD_SETTINGS_KEY))
    values = dict(DOWNLOAD_DEFAULTS)
    stored: dict[str, Any] = {}
    if row:
        try:
            decoded = json.loads(decrypt_secret(row.value))
            stored = decoded if isinstance(decoded, dict) else {}
            values.update(stored)
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    values["cookies"] = ""
    values["cookies_set"] = bool(stored.get("cookies"))
    return values


@app.get("/api/download/settings")
def read_download_settings(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    return _download_settings(db, user.id)


@app.put("/api/download/settings")
def update_download_settings(
    payload: DownloadSettings, user: CsrfUser, db: Annotated[Session, Depends(get_db)]
) -> dict[str, Any]:
    current = dict(DOWNLOAD_DEFAULTS)
    setting_key = f"{DOWNLOAD_SETTINGS_KEY}:{user.id}"
    row = db.scalar(select(AppSetting).where(AppSetting.key == setting_key))
    if row:
        try:
            stored = json.loads(decrypt_secret(row.value))
            if isinstance(stored, dict):
                current.update(stored)
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    current.update(payload.model_dump(exclude_none=True))
    encrypted = encrypt_secret(json.dumps(current, ensure_ascii=False))
    if row:
        row.value = encrypted
    else:
        db.add(AppSetting(key=setting_key, value=encrypted))
    db.commit()
    return _download_settings(db, user.id)


@app.post("/api/download/cookies/test")
def test_download_cookies(payload: DownloadCookieTest, user: CsrfUser) -> dict[str, Any]:
    lines = [line for line in payload.cookies.splitlines() if line.strip() and not line.startswith("#")]
    valid = all(len(line.split("\t")) >= 7 for line in lines)
    if not lines:
        raise HTTPException(status_code=400, detail="请先粘贴 Netscape 格式 Cookies")
    if not valid:
        raise HTTPException(status_code=400, detail="Cookies 格式无效，请粘贴 Netscape 格式文本")
    return {"valid": True, "message": f"Cookies 格式有效，共识别 {len(lines)} 条记录"}


@app.get("/api/download/cookies/status")
def download_cookies_status(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    row = db.scalar(select(AppSetting).where(AppSetting.key == f"{DOWNLOAD_SETTINGS_KEY}:{user.id}"))
    if not row:
        row = db.scalar(select(AppSetting).where(AppSetting.key == DOWNLOAD_SETTINGS_KEY))
    if not row:
        return {"configured": False, "valid": False, "message": "尚未保存 Cookies"}
    try:
        stored = json.loads(decrypt_secret(row.value))
        cookies = str(stored.get("cookies") or "") if isinstance(stored, dict) else ""
    except (ValueError, TypeError, json.JSONDecodeError):
        cookies = ""
    lines = [line for line in cookies.splitlines() if line.strip() and not line.startswith("#")]
    valid = bool(lines) and all(len(line.split("\t")) >= 7 for line in lines)
    return {"configured": bool(cookies), "valid": valid, "message": "已保存 Cookies，格式检查通过" if valid else "已保存 Cookies，但格式检查未通过"}


@app.post("/api/download/proxy/test")
def test_download_proxy(payload: DownloadProxyTest, user: CsrfUser) -> dict[str, Any]:
    if user.role not in {Role.admin, Role.editor}:
        raise HTTPException(status_code=403, detail="需要编辑权限")
    if not payload.proxy_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="代理测试目前支持 HTTP 或 HTTPS 地址")
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": payload.proxy_url, "https": payload.proxy_url}))
        with opener.open("https://www.youtube.com/", timeout=10) as response:
            if response.status >= 400:
                raise OSError(f"HTTP {response.status}")
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"代理连接失败：{exc}") from exc
    return {"valid": True, "message": "代理连接正常"}


@app.get("/api/download/proxy/status")
def download_proxy_status(user: CurrentUser) -> dict[str, Any]:
    """Report the server's public region before asking users to configure a proxy."""
    try:
        with urllib.request.urlopen("https://ipapi.co/json/", timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        country_code = str(payload.get("country_code") or "").upper()
        country = str(payload.get("country_name") or country_code or "未知")
        ip = str(payload.get("ip") or "未知")
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"无法查询服务器公网 IP 和地区：{exc}") from exc
    blocked = {"CN", "KP", "IR", "SY", "TM", "SD", "CU"}
    supported = country_code not in blocked
    return {
        "ip": ip,
        "country_code": country_code,
        "country": country,
        "youtube_supported": supported,
        "message": "当前服务器所在地区原生支持 YouTube，无需代理" if supported else "当前服务器所在地区访问 YouTube 可能受限，请配置可用代理",
    }


def _download_task_payload(task: DownloadTask) -> dict[str, Any]:
    return {"id": task.id, "url": task.url, "title": task.title or "待获取标题", "duration": task.duration or "-", "estimated_size": task.estimated_size or "-", "status": task.status, "progress": task.progress, "error": task.error}


def _owned_download_task(db: Session, task_id: int, user: User) -> DownloadTask | None:
    query = select(DownloadTask).where(DownloadTask.id == task_id)
    if user.role != Role.admin:
        query = query.where(DownloadTask.user_id == user.id)
    return db.scalar(query)


@app.get("/api/download/tasks")
def list_download_tasks(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict[str, Any]]:
    query = select(DownloadTask).order_by(DownloadTask.created_at.desc())
    if user.role != Role.admin:
        query = query.where(DownloadTask.user_id == user.id)
    return [_download_task_payload(task) for task in db.scalars(query).all()]


@app.get("/api/download/tasks/{task_id}/file")
def download_task_file(task_id: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> FileResponse:
    task = _owned_download_task(db, task_id, user)
    if not task or task.status != "completed" or not task.output_path:
        raise HTTPException(status_code=404, detail="下载文件不存在或任务尚未完成")
    output_dir = Path(task.output_path).resolve()
    data_root = get_settings().data_dir.resolve()
    if data_root not in output_dir.parents or not output_dir.is_dir():
        raise HTTPException(status_code=404, detail="下载文件目录不存在")
    files = [path for path in output_dir.iterdir() if path.is_file() and not path.name.startswith(".cookies-")]
    if not files:
        raise HTTPException(status_code=404, detail="下载文件不存在")
    with tempfile.NamedTemporaryFile(prefix=f"vx-download-{task_id}-", suffix=".zip", delete=False) as temporary:
        archive = Path(temporary.name)
    try:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in files:
                bundle.write(path, path.name)
    except OSError:
        archive.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="打包下载文件失败") from None
    return FileResponse(archive, media_type="application/zip", filename=f"vx-download-{task_id}.zip", background=BackgroundTask(lambda: archive.unlink(missing_ok=True)))


@app.post("/api/download/tasks", status_code=201)
def create_download_tasks(payload: DownloadTaskCreate, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> list[dict[str, Any]]:
    urls = [url.strip() for url in payload.urls if url.strip()]
    if not urls or any(not url.startswith(("https://www.youtube.com/", "https://youtu.be/")) for url in urls):
        raise HTTPException(status_code=400, detail="目前只支持 YouTube 视频或播放列表链接")
    _consume_usage(db, user, "download", len(urls))
    tasks = [DownloadTask(url=url, user_id=user.id) for url in urls]
    db.add_all(tasks)
    db.commit()
    return [_download_task_payload(task) for task in tasks]


@app.post("/api/download/tasks/{task_id}/start")
def start_download_task(task_id: int, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    task = _owned_download_task(db, task_id, user)
    if not task:
        raise HTTPException(status_code=404, detail="下载任务不存在")
    if task.status not in {"queued", "paused", "failed"}:
        raise HTTPException(status_code=400, detail="当前任务不能开始")
    task.status = "queued"
    db.commit()
    start_task(task.id)
    return _download_task_payload(task)


@app.post("/api/download/tasks/{task_id}/cancel")
def cancel_download_task(task_id: int, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    task = _owned_download_task(db, task_id, user)
    if not task:
        raise HTTPException(status_code=404, detail="下载任务不存在")
    task.status = "cancelled"
    db.commit()
    cancel_task(task_id)
    return _download_task_payload(task)


@app.post("/api/download/tasks/{task_id}/pause")
def pause_download_task(task_id: int, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    task = _owned_download_task(db, task_id, user)
    if not task or task.status != "downloading":
        raise HTTPException(status_code=400, detail="当前任务不能暂停")
    pause_task(task_id)
    task.status = "paused"
    db.commit()
    return _download_task_payload(task)


@app.post("/api/download/tasks/{task_id}/resume")
def resume_download_task(task_id: int, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    task = _owned_download_task(db, task_id, user)
    if not task or task.status != "paused":
        raise HTTPException(status_code=400, detail="当前任务不能继续")
    task.status = "queued"
    db.commit()
    start_task(task.id)
    return _download_task_payload(task)


@app.delete("/api/download/tasks/{task_id}", status_code=204)
def delete_download_task(task_id: int, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> None:
    task = _owned_download_task(db, task_id, user)
    if not task:
        raise HTTPException(status_code=404, detail="下载任务不存在")
    db.delete(task)
    db.commit()


@app.get("/api/setup/status")
def setup_status(db: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    return {"initialized": (db.scalar(select(func.count(User.id))) or 0) > 0}


@app.get("/api/auth/config")
def auth_config(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    values = auth_settings(db)
    return {
        "registration_enabled": values["registration_enabled"],
        "captcha_enabled": values["captcha_enabled"],
        "captcha_provider": values["captcha_provider"],
        "captcha_site_key": values["captcha_site_key"],
    }


@app.get("/api/settings/auth")
def read_auth_settings(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    values = auth_settings(db)
    return {**values, "smtp_password_set": bool(values.get("smtp_password")), "smtp_password": None, "captcha_secret_key_set": bool(values.get("captcha_secret_key")), "captcha_secret_key": None}


@app.put("/api/settings/auth")
def update_auth_settings(payload: AuthSettingsUpdate, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    current = auth_settings(db)
    # Settings forms are independent. Merge only fields actually submitted so
    # saving SMTP cannot reset captcha and vice versa.
    updates = payload.model_dump(exclude_unset=True)
    values = {**current, **updates}
    if not updates.get("smtp_password"):
        values["smtp_password"] = current.get("smtp_password")
    if not updates.get("captcha_secret_key"):
        values["captcha_secret_key"] = current.get("captcha_secret_key")
    save_auth_settings(db, values)
    db.commit()
    return {**values, "smtp_password_set": bool(values.get("smtp_password")), "smtp_password": None, "captcha_secret_key_set": bool(values.get("captcha_secret_key")), "captcha_secret_key": None}


@app.post("/api/settings/auth/test")
def test_auth_smtp(payload: SMTPTestRequest, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    test_smtp_connection(db, payload.recipient)
    return {"message": "测试邮件已发送"}


@app.post("/api/setup", status_code=201)
def setup(
    payload: SetupRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if (db.scalar(select(func.count(User.id))) or 0) > 0:
        raise HTTPException(status_code=409, detail="系统已经初始化")
    user = User(
        username=payload.username, password_hash=hash_password(payload.password), role=Role.admin, level=3
    )
    db.add(user)
    db.flush()
    raw_token, login_session = _create_session(db, user, request)
    write_audit(db, "system.setup", user, "user", user.id)
    db.commit()
    _set_session_cookie(request, response, raw_token)
    return _user_payload(user, login_session.csrf_token)


@app.post("/api/auth/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    require_captcha(request, payload.captcha_token, db)
    attempt_key = (
        f"{request.client.host if request.client else 'unknown'}:{payload.username.lower()}"
    )
    now = time.monotonic()
    attempts = [value for value in _login_attempts.get(attempt_key, []) if now - value < 300]
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 5 分钟后重试")
    user = db.scalar(select(User).where(
        (User.username == payload.username) | (User.email == normalize_email(payload.username))
    ))
    if not user or not user.is_active or not verify_password(user.password_hash, payload.password):
        attempts.append(now)
        _login_attempts[attempt_key] = attempts
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    _login_attempts.pop(attempt_key, None)
    user.last_login_at = datetime.now(UTC)
    raw_token, login_session = _create_session(db, user, request)
    write_audit(db, "auth.login", user, "session")
    db.commit()
    _set_session_cookie(request, response, raw_token)
    return _user_payload(user, login_session.csrf_token)


@app.post("/api/auth/register/request-code")
def register_request_code(payload: RegisterCodeRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    if not bool(auth_settings(db)["registration_enabled"]):
        raise HTTPException(status_code=404, detail="注册功能当前已关闭")
    require_captcha(request, payload.captcha_token, db)
    email = normalize_email(payload.email)
    if email_user(db, email):
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    send_code(db, email, "register")
    db.commit()
    return {"message": "验证码已发送"}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    if not bool(auth_settings(db)["registration_enabled"]):
        raise HTTPException(status_code=404, detail="注册功能当前已关闭")
    require_captcha(request, payload.captcha_token, db)
    email = normalize_email(payload.email)
    if db.scalar(select(User).where((User.username == payload.username) | (User.email == email))):
        raise HTTPException(status_code=409, detail="用户名或邮箱已存在")
    if not consume_code(db, email, "register", payload.code):
        raise HTTPException(status_code=422, detail="验证码错误或已过期")
    user = User(username=payload.username, email=email, email_verified=True,
                password_hash=hash_password(payload.password), role=Role.viewer, level=0)
    db.add(user)
    db.flush()
    raw_token, session = _create_session(db, user, request)
    write_audit(db, "auth.register", user, "user", user.id)
    db.commit()
    _set_session_cookie(request, response, raw_token)
    return _user_payload(user, session.csrf_token)


@app.post("/api/auth/password-reset/request-code")
def reset_request_code(payload: PasswordResetRequest, request: Request, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    require_captcha(request, payload.captcha_token, db)
    email = normalize_email(payload.email)
    if not email_user(db, email):
        # Avoid exposing whether an address is registered.
        return {"message": "如果邮箱已注册，验证码将发送至该邮箱"}
    send_code(db, email, "reset")
    db.commit()
    return {"message": "如果邮箱已注册，验证码将发送至该邮箱"}


@app.post("/api/auth/password-reset")
def reset_password(payload: PasswordResetConfirm, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    require_captcha(request, payload.captcha_token, db)
    email = normalize_email(payload.email)
    user = email_user(db, email)
    if not user or not consume_code(db, email, "reset", payload.code):
        raise HTTPException(status_code=422, detail="验证码错误或已过期")
    user.password_hash = hash_password(payload.new_password)
    db.execute(LoginSession.__table__.delete().where(LoginSession.user_id == user.id))
    raw_token, session = _create_session(db, user, request)
    write_audit(db, "auth.password.reset", user)
    db.commit()
    _set_session_cookie(request, response, raw_token)
    return _user_payload(user, session.csrf_token)


@app.get("/api/auth/me")
def me(
    request: Request, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> dict[str, Any]:
    raw_token = request.cookies.get("vx_session", "")
    login_session = db.scalar(
        select(LoginSession).where(LoginSession.token_hash == token_hash(raw_token))
    )
    return _user_payload(user, login_session.csrf_token if login_session else None)


@app.post("/api/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    raw_token = request.cookies.get("vx_session", "")
    login_session = db.scalar(
        select(LoginSession).where(LoginSession.token_hash == token_hash(raw_token))
    )
    user = db.get(User, login_session.user_id) if login_session else None
    if login_session:
        db.delete(login_session)
    write_audit(db, "auth.logout", user)
    db.commit()
    response.delete_cookie(
        "vx_session",
        path="/",
        secure=_secure_cookie(request),
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@app.post("/api/auth/change-password")
def change_password(
    payload: PasswordChange,
    request: Request,
    response: Response,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status_code=422, detail="当前密码错误")
    user.password_hash = hash_password(payload.new_password)
    db.execute(LoginSession.__table__.delete().where(LoginSession.user_id == user.id))
    raw_token, login_session = _create_session(db, user, request)
    write_audit(db, "auth.password.change", user)
    db.commit()
    _set_session_cookie(request, response, raw_token)
    return {"csrf_token": login_session.csrf_token}


@app.post("/api/auth/username")
def change_username(payload: UsernameChange, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    if db.scalar(select(User).where(User.username == payload.username, User.id != user.id)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    user.username = payload.username
    db.commit()
    return {"username": user.username}


@app.get("/api/auth/sessions")
def list_sessions(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    current_hash = token_hash(request.cookies.get("vx_session", ""))
    rows = db.scalars(
        select(LoginSession)
        .where(LoginSession.user_id == user.id)
        .order_by(LoginSession.last_seen_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "user_agent": row.user_agent,
            "created_at": row.created_at,
            "last_seen_at": row.last_seen_at,
            "expires_at": row.expires_at,
            "current": row.token_hash == current_hash,
        }
        for row in rows
    ]


@app.delete("/api/auth/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: int,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    login_session = db.get(LoginSession, session_id)
    if not login_session or login_session.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.delete(login_session)
    write_audit(db, "auth.session.revoke", user, "session", session_id)
    db.commit()


@app.get("/api/users")
def list_users(
    user: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    rows = db.scalars(select(User).order_by(User.created_at)).all()
    return [
        {
            "id": row.id,
            "username": row.username,
            "role": row.role.value,
            "level": row.level,
            "is_active": row.is_active,
            "email": row.email,
            "created_at": row.created_at,
            "last_login_at": row.last_login_at,
            "avatar": row.avatar or "default",
        }
        for row in rows
    ]


@app.post("/api/users", status_code=201)
def create_user(
    payload: UserCreate,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    email = normalize_email(payload.email)
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="注册邮箱已存在")
    created = User(
        username=payload.username,
        email=email,
        email_verified=True,
        password_hash=hash_password(payload.password),
        role=payload.role,
        level=payload.level,
        avatar=payload.avatar or "default",
    )
    db.add(created)
    db.flush()
    write_audit(db, "user.create", user, "user", created.id, {"role": created.role.value})
    db.commit()
    return {"id": created.id, "username": created.username, "role": created.role.value, "level": created.level}


@app.patch("/api/users/{user_id}")
def update_user(user_id: int, payload: UserAdminUpdate, user: Annotated[User, Depends(require_csrf_admin)], db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == user.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="不能停用当前登录用户")
    if payload.email is not None:
        normalized_email = normalize_email(payload.email) if payload.email else None
        if normalized_email and db.scalar(select(User).where(User.email == normalized_email, User.id != target.id)):
            raise HTTPException(status_code=409, detail="注册邮箱已被其他用户使用")
        target.email = normalized_email
        target.email_verified = bool(target.email)
    if payload.password:
        target.password_hash = hash_password(payload.password)
    if payload.role is not None:
        target.role = payload.role
    if payload.level is not None:
        target.level = payload.level
    if payload.is_active is not None:
        target.is_active = payload.is_active
    if payload.avatar is not None:
        target.avatar = payload.avatar or "default"
    write_audit(db, "user.update", user, "user", target.id)
    db.commit()
    return {"id": target.id, "username": target.username, "email": target.email, "role": target.role.value, "level": target.level, "is_active": target.is_active, "avatar": target.avatar or "default", "created_at": target.created_at, "last_login_at": target.last_login_at}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, user: Annotated[User, Depends(require_csrf_admin)], db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")
    db.delete(target)
    write_audit(db, "user.delete", user, "user", user_id)
    db.commit()
    return {"message": "用户已删除"}


@app.get("/api/accounts")
def list_accounts(
    user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> list[dict[str, Any]]:
    query = select(ChannelsAccount).order_by(ChannelsAccount.created_at)
    if user.role == Role.admin:
        query = query.where(ChannelsAccount.user_id.is_(None))
    else:
        query = query.where(ChannelsAccount.user_id == user.id)
    rows = db.scalars(query).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.post("/api/accounts", status_code=201)
def create_account(
    payload: AccountCreate,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if db.scalar(select(ChannelsAccount).where(ChannelsAccount.name == payload.name.strip())):
        raise HTTPException(status_code=409, detail="账号名称已存在")
    account = ChannelsAccount(name=payload.name.strip(), description=payload.description, user_id=None if user.role == Role.admin else user.id)
    db.add(account)
    db.flush()
    write_audit(db, "account.create", user, "account", account.id, {"name": account.name})
    db.commit()
    return {
        "id": account.id,
        "name": account.name,
        "description": account.description,
        "created_at": account.created_at,
    }


def _account_metric_values(row: Any) -> dict[str, Any]:
    return {
        "plays": row.plays,
        "recommendations": row.recommendations,
        "likes": row.likes,
        "comments": row.comments,
        "shares": row.shares,
        "follows": row.follows,
        "favorites": getattr(row, "favorites", None),
    }


def _preview_account_rows(db: Session, account_id: int, rows: list[Any]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        existing = db.scalar(
            select(DailyAccountMetric).where(
                DailyAccountMetric.account_id == account_id,
                DailyAccountMetric.metric_date == row.metric_date,
            )
        )
        incoming = _account_metric_values(row)
        if not existing:
            action = "new"
            differences = None
        else:
            current = _account_metric_values(existing)
            differences = {
                key: {"old": current[key], "new": incoming[key]}
                for key in incoming
                if current[key] != incoming[key]
            }
            action = "update" if differences else "duplicate"
        result.append(
            {
                "date": row.metric_date.isoformat(),
                **incoming,
                "action": action,
                "differences": differences,
            }
        )
    return result


@app.post("/api/imports/account-csv/preview")
def preview_account_csv(
    account_id: Annotated[int, Form()],
    data_end_date: Annotated[date, Form()],
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(require_csrf_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, account_id, user)
    content = _read_upload(file)
    try:
        rows = parse_account_csv(content)
    except ImportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if max(row.metric_date for row in rows) != data_end_date:
        raise HTTPException(
            status_code=422,
            detail=f"所选截止日期为 {data_end_date}，但文件最新日期为 {max(row.metric_date for row in rows)}，请确认没有选错日期",
        )
    preview = _preview_account_rows(db, account_id, rows)
    return {
        "filename": file.filename,
        "file_hash": file_sha256(content),
        "date_range": [min(row.metric_date for row in rows), max(row.metric_date for row in rows)],
        "record_count": len(rows),
        "summary": {
            action: sum(1 for item in preview if item["action"] == action)
            for action in ("new", "update", "duplicate")
        },
        "rows": preview,
    }


@app.post("/api/imports/account-csv/commit", status_code=201)
def commit_account_csv(
    account_id: Annotated[int, Form()],
    data_end_date: Annotated[date, Form()],
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(require_csrf_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, account_id, user)
    content = _read_upload(file)
    try:
        rows = parse_account_csv(content)
    except ImportValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if max(row.metric_date for row in rows) != data_end_date:
        raise HTTPException(
            status_code=422,
            detail=f"所选截止日期为 {data_end_date}，但文件最新日期为 {max(row.metric_date for row in rows)}，请确认没有选错日期",
        )
    batch = ImportBatch(
        account_id=account_id,
        user_id=user.id,
        import_type=ImportType.account_csv,
        status=ImportStatus.completed,
        filename=(file.filename or "data.csv")[:255],
        file_hash=file_sha256(content),
        record_count=len(rows),
    )
    db.add(batch)
    db.flush()
    counts = {"new": 0, "update": 0, "duplicate": 0}
    for index, row in enumerate(rows, start=1):
        existing = db.scalar(
            select(DailyAccountMetric).where(
                DailyAccountMetric.account_id == account_id,
                DailyAccountMetric.metric_date == row.metric_date,
            )
        )
        incoming = _account_metric_values(row)
        action = "new"
        if existing:
            current = _account_metric_values(existing)
            if current == incoming:
                action = "duplicate"
            else:
                action = "update"
                db.add(
                    DailyAccountMetricRevision(
                        metric_id=existing.id,
                        previous_json=json.dumps(current, ensure_ascii=False),
                        replacement_batch_id=batch.id,
                    )
                )
                for key, value in incoming.items():
                    setattr(existing, key, value)
                existing.source_batch_id = batch.id
        else:
            existing = DailyAccountMetric(
                account_id=account_id,
                metric_date=row.metric_date,
                source_batch_id=batch.id,
                **incoming,
            )
            db.add(existing)
        db.add(
            ImportRow(
                batch_id=batch.id,
                row_number=index,
                raw_json=json.dumps(row.raw, ensure_ascii=False),
                normalized_json=json.dumps(row.normalized(), ensure_ascii=False, default=str),
            )
        )
        counts[action] += 1
    write_audit(db, "import.account_csv", user, "import_batch", batch.id, counts)
    db.commit()
    return {"batch_id": batch.id, "record_count": len(rows), "summary": counts}


@app.post("/api/imports/video-sheet/preview")
def preview_video_sheet(
    account_id: Annotated[int, Form()],
    metric_date: Annotated[date, Form()],
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(require_csrf_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, account_id, user)
    content = _read_upload(file)
    try:
        rows = parse_video_sheet(content, file.filename or "")
    except (ImportValidationError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for row in rows:
        row["metric_date"] = metric_date
    return {
        "filename": file.filename,
        "file_hash": file_sha256(content),
        "record_count": len(rows),
        "rows": [{**row, "raw": None} for row in rows],
    }


@app.post("/api/imports/screenshots/recognize")
def recognize_screenshots(
    metric_date: Annotated[date, Form()],
    files: Annotated[list[UploadFile], File()],
    user: Annotated[User, Depends(require_csrf_editor)],
) -> dict[str, Any]:
    if len(files) > 30:
        raise HTTPException(status_code=422, detail="一次最多上传 30 张截图")
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for file in files:
        try:
            content = _read_upload(file)
        except HTTPException as exc:
            errors.append({"filename": file.filename or "截图", "error": str(exc.detail)})
            continue
        try:
            candidates.extend(
                extract_screenshot_candidates(content, metric_date, file.filename or "截图")
            )
        except (ValueError, OCRUnavailableError, OSError, RuntimeError) as exc:
            errors.append({"filename": file.filename or "截图", "error": str(exc)})
    gc.collect()
    return {
        "metric_date": metric_date,
        "input_files": len(files),
        "recognized_before_dedup": len(candidates),
        "candidates": deduplicate_candidates(candidates),
        "errors": errors,
    }


@app.post("/api/imports/video-metrics/commit", status_code=201)
def commit_video_metrics(
    payload: VideoMetricCommit,
    user: Annotated[User, Depends(require_csrf_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, payload.account_id, user)
    rows = payload.rows
    if payload.metric_date:
        rows = [row.model_copy(update={"metric_date": payload.metric_date}) for row in rows]
    batch = ImportBatch(
        account_id=payload.account_id,
        user_id=user.id,
        import_type=ImportType.screenshot,
        status=ImportStatus.completed,
        filename=(payload.filename or "人工确认")[:255],
        record_count=len(rows),
    )
    db.add(batch)
    db.flush()
    created = updated = 0
    for index, row in enumerate(rows, start=1):
        identity_key = video_identity(row.title, row.published_at, row.identity_key)
        video = db.scalar(
            select(Video).where(
                Video.account_id == payload.account_id, Video.identity_key == identity_key
            )
        )
        if not video:
            video = Video(
                account_id=payload.account_id,
                identity_key=identity_key,
                title=row.title,
                published_at=row.published_at,
            )
            db.add(video)
            db.flush()
        metric = db.scalar(
            select(DailyVideoMetric).where(
                DailyVideoMetric.video_id == video.id,
                DailyVideoMetric.metric_date == row.metric_date,
            )
        )
        values = row.model_dump(exclude={"title", "published_at", "metric_date", "identity_key"})
        if metric:
            for key, value in values.items():
                setattr(metric, key, value)
            metric.source_batch_id = batch.id
            updated += 1
        else:
            db.add(
                DailyVideoMetric(
                    video_id=video.id,
                    metric_date=row.metric_date,
                    source_batch_id=batch.id,
                    **values,
                )
            )
            created += 1
        db.add(
            ImportRow(
                batch_id=batch.id,
                row_number=index,
                raw_json=row.model_dump_json(),
                normalized_json=json.dumps(
                    {"video_id": video.id, **row.model_dump(mode="json")}, ensure_ascii=False
                ),
            )
        )
    write_audit(
        db,
        "import.video_metrics",
        user,
        "import_batch",
        batch.id,
        {"created": created, "updated": updated},
    )
    db.commit()
    return {"batch_id": batch.id, "created": created, "updated": updated}


@app.get("/api/imports")
def import_history(
    account_id: int | None = None,
    limit: int = 50,
    user: CurrentUser = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = (
        select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(min(max(limit, 1), 200))
    )
    if account_id:
        query = query.where(ImportBatch.account_id == account_id)
    rows = db.scalars(query).all()
    return [
        {
            "id": row.id,
            "account_id": row.account_id,
            "type": row.import_type.value,
            "status": row.status.value,
            "filename": row.filename,
            "record_count": row.record_count,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.get("/api/templates/video-metrics.csv")
def video_metrics_template(user: CurrentUser) -> FastAPIResponse:
    content = (
        "\ufeff数据日期,视频标识,视频标题,发布时间,当日播放量,累计播放量,喜欢,评论,分享\r\n"
        "2026-08-16,,示例视频,2026-08-14 21:49:00,600,1300,30,8,15\r\n"
    )
    return FastAPIResponse(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="video_metrics_template.csv"'},
    )


@app.get("/api/analytics/day")
def day_analytics(
    account_id: int,
    metric_date: date,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, account_id, user)
    return date_summary(db, account_id, metric_date)


@app.get("/api/analytics/available-dates")
def available_analytics_dates(
    account_id: int,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, account_id, user)
    today = date.today()
    rows = db.scalars(
        select(DailyAccountMetric.metric_date)
        .where(DailyAccountMetric.account_id == account_id, DailyAccountMetric.metric_date <= today)
        .order_by(DailyAccountMetric.metric_date)
    ).all()
    dates = [value.isoformat() for value in rows]
    return {"dates": dates, "earliest_date": dates[0] if dates else None, "latest_date": dates[-1] if dates else None}


@app.get("/api/analytics/range")
def range_analytics(
    account_id: int,
    start_date: date,
    end_date: date,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, account_id, user)
    if end_date < start_date or (end_date - start_date).days > 366:
        raise HTTPException(status_code=422, detail="日期范围无效或超过 366 天")
    return range_summary(db, account_id, start_date, end_date)


@app.get("/api/analytics/videos")
def video_range_analytics(
    account_id: int,
    start_date: date,
    end_date: date,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, account_id, user)
    if end_date < start_date or (end_date - start_date).days > 366:
        raise HTTPException(status_code=422, detail="日期范围无效或超过 366 天")
    return range_video_summary(db, account_id, start_date, end_date)


def _provider_payload(config: AIProviderConfig) -> dict[str, Any]:
    try:
        models = json.loads(config.models_json) if config.models_json else []
    except (TypeError, json.JSONDecodeError):
        models = []
    if not isinstance(models, list):
        models = []
    models = [str(item) for item in models if str(item).strip()]
    if config.model and config.model not in models:
        models.insert(0, config.model)
    return {
        "id": config.id,
        "account_id": config.account_id,
        "name": config.name,
        "base_url": config.base_url,
        "model": config.model,
        "models": models,
        "protocol": config.protocol,
        "interface_type": config.interface_type,
        "timeout_seconds": config.timeout_seconds,
        "api_key_configured": bool(config.encrypted_api_key),
        "is_active": config.is_active,
    }


def _provider_candidates(db: Session, account_id: int, user: User | None = None) -> list[AIProviderConfig]:
    _get_account(db, account_id, user)
    # New configurations are global. Keep legacy account-scoped rows readable
    # for administrators so they can promote them by editing once.
    if user is not None and user.role.value != "admin":
        return list(db.scalars(
            select(AIProviderConfig)
            .outerjoin(ChannelsAccount, AIProviderConfig.account_id == ChannelsAccount.id)
            .where((AIProviderConfig.account_id.is_(None)) | ChannelsAccount.user_id.is_(None))
            .order_by(AIProviderConfig.id)
        ).all())
    return list(
        db.scalars(
            select(AIProviderConfig)
            .where(
                (AIProviderConfig.account_id == account_id)
                | (AIProviderConfig.account_id.is_(None))
            )
            .order_by(AIProviderConfig.account_id.is_(None), AIProviderConfig.id)
        ).all()
    )


def _active_provider(db: Session, account_id: int, user: User | None = None) -> AIProviderConfig | None:
    rows = _provider_candidates(db, account_id, user)
    return next((row for row in rows if row.account_id is None and row.is_active), None) or next(
        (row for row in rows if row.account_id == account_id and row.is_active), None
    )


def _chat_category_payload(row: AIChatCategory) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "sort_order": row.sort_order, "pinned": row.pinned, "provider_id": row.provider_id, "created_at": row.created_at, "updated_at": row.updated_at}


def _chat_session_payload(row: AIChatSession) -> dict[str, Any]:
    return {"id": row.id, "category_id": row.category_id, "title": row.title, "pinned": row.pinned, "provider_id": row.provider_id, "created_at": row.created_at, "updated_at": row.updated_at}


def _chat_owned_session(db: Session, session_id: int, user: User) -> AIChatSession:
    row = db.scalar(select(AIChatSession).where(AIChatSession.id == session_id, AIChatSession.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="聊天不存在")
    return row


def _chat_message_content(db: Session, message: AIChatMessage) -> str | list[dict[str, Any]]:
    """Rebuild a stored user message, including its attachments, for stateless AI APIs."""
    attachments = db.scalars(select(AIChatAttachment).where(AIChatAttachment.message_id == message.id).order_by(AIChatAttachment.id)).all()
    if not attachments:
        return message.content
    parts: list[dict[str, Any]] = []
    if message.content:
        parts.append({"type": "text", "text": message.content})
    for attachment in attachments:
        path = Path(attachment.storage_path).resolve()
        if not path.is_file():
            continue
        raw = path.read_bytes()
        if attachment.content_type.startswith("image/"):
            parts.append({"type": "image_url", "image_url": {"url": f"data:{attachment.content_type};base64,{base64.b64encode(raw).decode()}"}})
        else:
            parts.append({"type": "text", "text": f"\n[附件 {attachment.filename}]\n{raw.decode('utf-8', errors='replace')}"})
    return parts or message.content


@app.get("/api/ai-chat/categories")
def list_chat_categories(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict[str, Any]]:
    return [_chat_category_payload(row) for row in db.scalars(select(AIChatCategory).where(AIChatCategory.user_id == user.id).order_by(AIChatCategory.pinned.desc(), AIChatCategory.pinned_at.desc().nullslast(), AIChatCategory.sort_order, AIChatCategory.id)).all()]


@app.post("/api/ai-chat/categories", status_code=201)
def create_chat_category(payload: AIChatCategoryInput, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    max_order = db.scalar(select(func.max(AIChatCategory.sort_order)).where(AIChatCategory.user_id == user.id)) or -1
    row = AIChatCategory(user_id=user.id, name=payload.name.strip(), sort_order=payload.sort_order if payload.sort_order is not None else max_order + 1, provider_id=payload.provider_id, pinned=bool(payload.pinned))
    db.add(row); db.commit(); db.refresh(row)
    return _chat_category_payload(row)


@app.patch("/api/ai-chat/categories/{category_id}")
def update_chat_category(category_id: int, payload: AIChatCategoryInput, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    row = db.scalar(select(AIChatCategory).where(AIChatCategory.id == category_id, AIChatCategory.user_id == user.id))
    if not row: raise HTTPException(status_code=404, detail="分类不存在")
    row.name = payload.name.strip()
    if payload.sort_order is not None: row.sort_order = payload.sort_order
    if payload.pinned is not None:
        row.pinned = payload.pinned
        row.pinned_at = datetime.now(UTC) if payload.pinned else None
    if payload.provider_id is not None: row.provider_id = payload.provider_id
    db.commit(); return _chat_category_payload(row)


@app.delete("/api/ai-chat/categories/{category_id}", status_code=204)
def delete_chat_category(category_id: int, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> Response:
    row = db.scalar(select(AIChatCategory).where(AIChatCategory.id == category_id, AIChatCategory.user_id == user.id))
    if not row: raise HTTPException(status_code=404, detail="分类不存在")
    db.delete(row); db.commit(); return Response(status_code=204)


@app.get("/api/ai-chat/sessions")
def list_chat_sessions(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict[str, Any]]:
    rows = db.scalars(select(AIChatSession).where(AIChatSession.user_id == user.id).order_by(AIChatSession.pinned.desc(), AIChatSession.pinned_at.desc().nullslast(), AIChatSession.updated_at.desc())).all()
    return [_chat_session_payload(row) for row in rows]


@app.post("/api/ai-chat/sessions", status_code=201)
def create_chat_session(payload: AIChatSessionInput, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    if payload.category_id and not db.scalar(select(AIChatCategory).where(AIChatCategory.id == payload.category_id, AIChatCategory.user_id == user.id)):
        raise HTTPException(status_code=404, detail="分类不存在")
    category = db.scalar(select(AIChatCategory).where(AIChatCategory.id == payload.category_id, AIChatCategory.user_id == user.id)) if payload.category_id else None
    row = AIChatSession(user_id=user.id, category_id=payload.category_id, title=payload.title.strip(), provider_id=payload.provider_id or (category.provider_id if category else None))
    db.add(row); db.commit(); db.refresh(row); return _chat_session_payload(row)


@app.patch("/api/ai-chat/sessions/{session_id}")
def update_chat_session(session_id: int, payload: AIChatSessionUpdate, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    row = _chat_owned_session(db, session_id, user)
    if payload.title is not None: row.title = payload.title.strip()
    if payload.category_id is not None:
        if not db.scalar(select(AIChatCategory).where(AIChatCategory.id == payload.category_id, AIChatCategory.user_id == user.id)): raise HTTPException(status_code=404, detail="分类不存在")
        row.category_id = payload.category_id
    if payload.pinned is not None:
        row.pinned = payload.pinned
        row.pinned_at = datetime.now(UTC) if payload.pinned else None
    if payload.provider_id is not None: row.provider_id = payload.provider_id
    db.commit(); return _chat_session_payload(row)


@app.get("/api/ai-chat/sessions/{session_id}/messages")
def list_chat_messages(session_id: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict[str, Any]]:
    _chat_owned_session(db, session_id, user)
    rows = db.scalars(select(AIChatMessage).where(AIChatMessage.session_id == session_id).order_by(AIChatMessage.created_at, AIChatMessage.id)).all()
    return [{"id": row.id, "role": row.role, "content": row.content, "created_at": row.created_at, "attachments": [{"id": item.id, "filename": item.filename, "content_type": item.content_type, "size_bytes": item.size_bytes} for item in db.scalars(select(AIChatAttachment).where(AIChatAttachment.message_id == row.id)).all()]} for row in rows]


def _chat_message_owned(db: Session, message_id: int, user: User) -> AIChatMessage:
    row = db.scalar(
        select(AIChatMessage)
        .join(AIChatSession, AIChatMessage.session_id == AIChatSession.id)
        .where(AIChatMessage.id == message_id, AIChatSession.user_id == user.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="消息不存在")
    return row


@app.patch("/api/ai-chat/messages/{message_id}")
def update_chat_message(
    message_id: int,
    payload: AIChatMessageUpdate,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    row = _chat_message_owned(db, message_id, user)
    if row.role != "user":
        raise HTTPException(status_code=403, detail="只能编辑用户消息")
    if not payload.content.strip() and not db.scalar(
        select(AIChatAttachment).where(AIChatAttachment.message_id == row.id)
    ):
        raise HTTPException(status_code=422, detail="消息内容和附件不能同时为空")
    row.content = payload.content.strip()
    db.commit()
    return {"id": row.id, "role": row.role, "content": row.content}


@app.delete("/api/ai-chat/messages/{message_id}", status_code=204)
def delete_chat_message(
    message_id: int,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    row = _chat_message_owned(db, message_id, user)
    if row.role != "user":
        raise HTTPException(status_code=403, detail="只能删除用户消息")
    attachment_rows = db.scalars(
        select(AIChatAttachment).where(AIChatAttachment.message_id == row.id)
    ).all()
    for attachment in attachment_rows:
        Path(attachment.storage_path).unlink(missing_ok=True)
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@app.delete("/api/ai-chat/sessions/{session_id}/messages", status_code=204)
def clear_chat_messages(
    session_id: int,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    _chat_owned_session(db, session_id, user)
    rows = db.scalars(
        select(AIChatMessage).where(AIChatMessage.session_id == session_id)
    ).all()
    for row in rows:
        for attachment in db.scalars(
            select(AIChatAttachment).where(AIChatAttachment.message_id == row.id)
        ).all():
            Path(attachment.storage_path).unlink(missing_ok=True)
        db.delete(row)
    db.commit()
    return Response(status_code=204)


@app.get("/api/ai-chat/attachments/{attachment_id}")
def get_chat_attachment(attachment_id: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> FileResponse:
    attachment = db.scalar(select(AIChatAttachment).where(AIChatAttachment.id == attachment_id))
    if not attachment:
        raise HTTPException(status_code=404, detail="附件不存在")
    message_row = db.get(AIChatMessage, attachment.message_id)
    if not message_row or not db.scalar(select(AIChatSession).where(AIChatSession.id == message_row.session_id, AIChatSession.user_id == user.id)):
        raise HTTPException(status_code=404, detail="附件不存在")
    path = Path(attachment.storage_path).resolve()
    data_root = (get_settings().data_dir / "ai-chat-attachments").resolve()
    if data_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件不存在")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.filename)


@app.get("/api/ai-chat/sessions/{session_id}/export")
def export_chat_session(session_id: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)], format: str = Query("markdown", pattern="^(markdown|json)$")) -> Response:
    row = _chat_owned_session(db, session_id, user)
    messages = db.scalars(select(AIChatMessage).where(AIChatMessage.session_id == session_id).order_by(AIChatMessage.created_at, AIChatMessage.id)).all()
    if format == "json":
        payload = {"title": row.title, "category_id": row.category_id, "created_at": row.created_at.isoformat(), "messages": [{"role": item.role, "content": item.content, "created_at": item.created_at.isoformat()} for item in messages]}
        return Response(content=json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="ai-chat-{session_id}.json"'})
    lines = [f"# {row.title}", ""]
    for item in messages:
        lines.extend([f"## {'用户' if item.role == 'user' else 'AI'}", "", item.content or "（附件消息）", ""])
    return Response(content="\n".join(lines), media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="ai-chat-{session_id}.md"'})


@app.delete("/api/ai-chat/sessions/{session_id}", status_code=204)
def delete_chat_session(session_id: int, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> Response:
    row = _chat_owned_session(db, session_id, user); attachment_dir = get_settings().data_dir / "ai-chat-attachments" / str(session_id); db.delete(row); db.commit(); shutil.rmtree(attachment_dir, ignore_errors=True); return Response(status_code=204)


USAGE_LIMITS = {0: {"ai_chat": 20, "analysis": 5, "download": 5}, 1: {"ai_chat": 50, "analysis": 10, "download": 20}, 2: {"ai_chat": 100, "analysis": 20, "download": 50}}


def _consume_usage(db: Session, user: User, kind: str, amount: int = 1) -> None:
    if user.role.value == "admin" or user.level >= 3:
        return
    limit = USAGE_LIMITS.get(user.level, USAGE_LIMITS[0]).get(kind)
    if limit is None:
        return
    today = datetime.now(UTC).date()
    counter = db.scalar(select(UsageCounter).where(UsageCounter.user_id == user.id, UsageCounter.usage_date == today, UsageCounter.kind == kind))
    if counter is None:
        counter = UsageCounter(user_id=user.id, usage_date=today, kind=kind, count=0); db.add(counter); db.flush()
    if counter.count + amount > limit:
        raise HTTPException(status_code=429, detail=f"今日{kind}额度已用尽（上限 {limit} 次）")
    counter.count += amount
    db.commit()


@app.post("/api/ai-chat/sessions/{session_id}/messages")
async def send_chat_message(session_id: int, payload: AIChatMessageInput, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> StreamingResponse:
    _consume_usage(db, user, "ai_chat")
    row = _chat_owned_session(db, session_id, user)
    config = db.get(AIProviderConfig, payload.provider_id or row.provider_id) if (payload.provider_id or row.provider_id) else db.scalar(select(AIProviderConfig).where(AIProviderConfig.is_active.is_(True)).order_by(AIProviderConfig.id))
    if not config: raise HTTPException(status_code=409, detail="请先配置并选择 AI 接口")
    if user.role.value != "admin" and config.account_id is not None:
        raise HTTPException(status_code=403, detail="该 AI 接口不是管理员发布的全局配置")
    if config.account_id is not None and not db.get(ChannelsAccount, config.account_id): raise HTTPException(status_code=404, detail="AI 配置不存在")
    if not payload.content.strip() and not payload.attachments:
        raise HTTPException(status_code=422, detail="消息内容和附件不能同时为空")
    attachment_dir = get_settings().data_dir / "ai-chat-attachments" / str(row.id)
    content_parts: list[dict[str, Any]] = [{"type": "text", "text": payload.content.strip()}] if payload.content.strip() else []
    attachment_rows: list[AIChatAttachment] = []
    allowed_attachment = lambda content_type, filename: (
        content_type.startswith("image/")
        or content_type.startswith("text/")
        or filename.lower().endswith((".txt", ".md", ".csv", ".json"))
    )
    total_attachment_size = 0
    for item in payload.attachments:
        filename = Path(item.get("filename", "attachment")).name[:255]
        content_type = item.get("content_type", "application/octet-stream")
        if not allowed_attachment(content_type, filename):
            raise HTTPException(status_code=415, detail=f"附件 {filename} 类型不受支持，仅支持图片和文本文件")
        encoded = item.get("data", "")
        if "," in encoded and encoded.startswith("data:"): encoded = encoded.split(",", 1)[1]
        try: raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError): raise HTTPException(status_code=422, detail=f"附件 {filename} 编码无效") from None
        if len(raw) > 10 * 1024 * 1024: raise HTTPException(status_code=413, detail=f"附件 {filename} 不能超过 10 MB")
        total_attachment_size += len(raw)
        if total_attachment_size > 32 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="附件总大小不能超过 32 MB")
        attachment_dir.mkdir(parents=True, exist_ok=True)
        target = attachment_dir / f"{uuid.uuid4().hex}-{filename}"
        target.write_bytes(raw)
        attachment_rows.append(AIChatAttachment(message_id=0, filename=filename, content_type=content_type, storage_path=str(target), size_bytes=len(raw)))
        if content_type.startswith("image/"):
            content_parts.append({"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{base64.b64encode(raw).decode()}"}})
        elif content_type.startswith("text/") or filename.lower().endswith((".txt", ".md", ".csv", ".json")):
            content_parts.append({"type": "text", "text": f"\n[附件 {filename}]\n{raw.decode('utf-8', errors='replace')}"})
    previous = db.scalars(select(AIChatMessage).where(AIChatMessage.session_id == row.id).order_by(AIChatMessage.created_at, AIChatMessage.id)).all()
    user_message = AIChatMessage(session_id=row.id, role="user", content=payload.content.strip(), provider_snapshot_json=json.dumps({"model": config.model, "base_url": config.base_url}, ensure_ascii=False))
    db.add(user_message); db.flush()
    for attachment in attachment_rows: attachment.message_id = user_message.id; db.add(attachment)
    db.commit()
    messages = [{"role": item.role, "content": _chat_message_content(db, item)} for item in previous[-20:]] + [{"role": "user", "content": content_parts}]
    async def event_stream():
        parts: list[str] = []
        try:
            async for part in stream_chat_provider(config, messages):
                parts.append(part); yield f"data: {json.dumps({'type': 'delta', 'content': part}, ensure_ascii=False)}\n\n"
            answer = "".join(parts)
            with SessionLocal() as stream_db:
                stream_db.add(AIChatMessage(session_id=row.id, role="assistant", content=answer, provider_snapshot_json=json.dumps({"model": config.model}, ensure_ascii=False))); stream_db.commit()
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/ai/providers")
def list_ai_providers(
    account_id: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> list[dict[str, Any]]:
    if user.role.value == "admin":
        _get_account(db, account_id, user)
        rows = db.scalars(
            select(AIProviderConfig)
            .outerjoin(ChannelsAccount, AIProviderConfig.account_id == ChannelsAccount.id)
            .where((AIProviderConfig.account_id.is_(None)) | ChannelsAccount.user_id.is_(None))
            .order_by(AIProviderConfig.account_id.is_(None).desc(), AIProviderConfig.id)
        ).all()
    else:
        rows = _provider_candidates(db, account_id, user)
    return [_provider_payload(row) for row in rows]


@app.get("/api/ai/providers/{provider_id}/models")
async def list_ai_provider_models(
    provider_id: int,
    account_id: int,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, list[str]]:
    """Return models available from a configured provider for the current user."""
    _get_account(db, account_id, user)
    config = db.get(AIProviderConfig, provider_id)
    if not config or not config.is_active:
        raise HTTPException(status_code=404, detail="接口配置不存在")
    allowed = _provider_candidates(db, account_id, user)
    if config.id not in {row.id for row in allowed}:
        raise HTTPException(status_code=403, detail="无权使用此接口配置")
    try:
        models = await list_provider_models(
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
            api_key=decrypt_secret(config.encrypted_api_key),
            protocol=config.protocol,
        )
    except Exception:
        # Keep the configured default usable when a provider's model listing is unavailable.
        models = []
    if config.model and config.model not in models:
        models.insert(0, config.model)
    return {"models": models}


@app.get("/api/ai/provider")
def get_ai_provider(
    account_id: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> dict[str, Any] | None:
    config = _active_provider(db, account_id, user)
    return _provider_payload(config) if config else None


@app.put("/api/ai/provider")
def save_ai_provider(
    payload: AIProviderInput,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, payload.account_id, user)
    config = None
    if payload.provider_id:
        config = db.scalar(
            select(AIProviderConfig).where(
                AIProviderConfig.id == payload.provider_id,
            )
        )
        if not config:
            raise HTTPException(status_code=404, detail="接口配置不存在")
    if not config:
        if not payload.api_key:
            raise HTTPException(status_code=422, detail="首次配置必须填写 API Key")
        config = AIProviderConfig(
            encrypted_api_key=encrypt_secret(payload.api_key),
            base_url=payload.base_url,
            model=payload.model,
            account_id=None,
        )
        db.add(config)
    else:
        # Editing a legacy account-scoped row promotes it to the administrator's
        # global registry instead of keeping a hidden per-account copy.
        config.account_id = None
    config.name = payload.name
    config.base_url = payload.base_url
    config.model = payload.model
    config.models_json = json.dumps(
        list(dict.fromkeys([item.strip() for item in payload.models if item.strip()])),
        ensure_ascii=False,
    ) if payload.models else config.models_json
    config.protocol = payload.protocol
    config.interface_type = payload.interface_type
    config.timeout_seconds = payload.timeout_seconds
    db.execute(
        AIProviderConfig.__table__.update()
        .where(AIProviderConfig.account_id.is_(None))
        .values(is_active=False)
    )
    config.is_active = True
    if payload.api_key:
        config.encrypted_api_key = encrypt_secret(payload.api_key)
    db.flush()
    write_audit(
        db,
        "ai.provider.save",
        user,
        "ai_provider",
        config.id,
        {"base_url": config.base_url, "model": config.model, "protocol": config.protocol},
    )
    db.commit()
    return {"id": config.id, "saved": True}


@app.post("/api/ai/provider/select")
def select_ai_provider(
    payload: AIProviderSelect,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, payload.account_id, user)
    config = db.scalar(
        select(AIProviderConfig).where(
            AIProviderConfig.id == payload.provider_id,
            (AIProviderConfig.account_id == payload.account_id)
            | (AIProviderConfig.account_id.is_(None)),
        )
    )
    if not config:
        raise HTTPException(status_code=404, detail="接口配置不存在")
    if config.account_id is not None and user.role.value != "admin":
        raise HTTPException(status_code=403, detail="仅可选择管理员发布的全局接口配置")
    db.execute(
        AIProviderConfig.__table__.update()
        .where(AIProviderConfig.account_id.is_(None))
        .values(is_active=False)
    )
    config.is_active = True
    write_audit(db, "ai.provider.select", user, "ai_provider", config.id)
    db.commit()
    return _provider_payload(config)


def _quick_config_payload(row: AIQuickConfig) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "provider_id": row.provider_id, "model": row.model, "created_at": row.created_at, "updated_at": row.updated_at}


def _provider_models(config: AIProviderConfig) -> set[str]:
    return set(_provider_payload(config)["models"])


def _owned_provider(db: Session, provider_id: int, user: User) -> AIProviderConfig:
    row = db.scalar(select(AIProviderConfig).outerjoin(ChannelsAccount, AIProviderConfig.account_id == ChannelsAccount.id).where(AIProviderConfig.id == provider_id, ((ChannelsAccount.user_id == user.id) | ChannelsAccount.user_id.is_(None) | AIProviderConfig.account_id.is_(None))))
    if not row:
        raise HTTPException(status_code=404, detail="接口配置不存在或无权使用")
    return row


@app.get("/api/ai/quick-configs")
def list_quick_configs(user: CurrentUser, db: Annotated[Session, Depends(get_db)]) -> list[dict[str, Any]]:
    rows = db.scalars(select(AIQuickConfig).where(AIQuickConfig.user_id == user.id).order_by(AIQuickConfig.created_at, AIQuickConfig.id)).all()
    return [{**_quick_config_payload(row), "associated_count": db.scalar(select(func.count(AIQueryHistory.id)).where(AIQueryHistory.provider_id == row.provider_id)) or 0} for row in rows]


@app.post("/api/ai/quick-configs", status_code=201)
def create_quick_config(payload: AIQuickConfigInput, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    if db.scalar(select(func.count(AIQuickConfig.id)).where(AIQuickConfig.user_id == user.id)) >= 5:
        raise HTTPException(status_code=409, detail="每个用户最多保存 5 个快捷配置")
    provider = _owned_provider(db, payload.provider_id, user)
    if payload.model not in _provider_models(provider):
        raise HTTPException(status_code=422, detail="模型必须来自已配置接口")
    row = AIQuickConfig(user_id=user.id, provider_id=provider.id, name=payload.name.strip(), model=payload.model)
    db.add(row); db.commit(); db.refresh(row)
    return _quick_config_payload(row)


@app.patch("/api/ai/quick-configs/{config_id}")
def update_quick_config(config_id: int, payload: AIQuickConfigInput, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    row = db.scalar(select(AIQuickConfig).where(AIQuickConfig.id == config_id, AIQuickConfig.user_id == user.id))
    if not row: raise HTTPException(status_code=404, detail="快捷配置不存在")
    provider = _owned_provider(db, payload.provider_id, user)
    if payload.model not in _provider_models(provider): raise HTTPException(status_code=422, detail="模型必须来自已配置接口")
    row.name = payload.name.strip(); row.provider_id = provider.id; row.model = payload.model
    db.commit(); return _quick_config_payload(row)


@app.delete("/api/ai/quick-configs/{config_id}", status_code=204)
def delete_quick_config(config_id: int, user: CsrfUser, db: Annotated[Session, Depends(get_db)]) -> Response:
    row = db.scalar(select(AIQuickConfig).where(AIQuickConfig.id == config_id, AIQuickConfig.user_id == user.id))
    if not row: raise HTTPException(status_code=404, detail="快捷配置不存在")
    db.delete(row); db.commit(); return Response(status_code=204)


@app.delete("/api/ai/provider/{provider_id}", status_code=204)
def delete_ai_provider(
    provider_id: int,
    account_id: int,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    _get_account(db, account_id, user)
    config = db.scalar(
        select(AIProviderConfig).where(
            AIProviderConfig.id == provider_id,
            (AIProviderConfig.account_id == account_id) | AIProviderConfig.account_id.is_(None),
        )
    )
    if not config:
        raise HTTPException(status_code=404, detail="接口配置不存在或不属于当前视频号")
    try:
        db.delete(config)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该配置已被历史分析记录使用，不能删除；可以重新编辑并停用它") from exc
    write_audit(db, "ai.provider.delete", user, "ai_provider", provider_id)
    db.commit()
    return Response(status_code=204)


@app.post("/api/ai/provider/test-and-save")
async def test_and_save_ai_provider(
    payload: AIProviderInput,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    existing = None
    if payload.provider_id:
        existing = db.scalar(
            select(AIProviderConfig).where(
                AIProviderConfig.id == payload.provider_id,
            )
        )
    if not existing:
        existing = _active_provider(db, payload.account_id)
    api_key = payload.api_key
    if not api_key and existing:
        api_key = decrypt_secret(existing.encrypted_api_key)
    if not api_key:
        raise HTTPException(status_code=422, detail="首次配置必须填写 API Key")
    try:
        result = await test_provider_values(
            base_url=payload.base_url,
            model=payload.model,
            protocol=payload.protocol,
            timeout_seconds=payload.timeout_seconds,
            api_key=api_key,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    saved = save_ai_provider(payload, user, db)
    return {**saved, "result": result}


@app.post("/api/ai/provider/test")
async def test_ai_provider(
    account_id: int,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    config = _active_provider(db, account_id)
    if not config:
        raise HTTPException(status_code=404, detail="尚未配置 AI")
    try:
        result = await test_provider(config)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    write_audit(db, "ai.provider.test", user, "ai_provider", config.id)
    db.commit()
    return {"result": result}


def _draft_api_key(payload: AIProviderDraft, db: Session) -> str:
    if payload.api_key:
        return payload.api_key
    existing = None
    if payload.provider_id:
        existing = db.scalar(
            select(AIProviderConfig).where(
                AIProviderConfig.id == payload.provider_id,
            )
        )
    if not existing:
        existing = _active_provider(db, payload.account_id)
    if existing:
        return decrypt_secret(existing.encrypted_api_key)
    raise HTTPException(status_code=422, detail="请填写 API Key")


@app.post("/api/ai/provider/models")
async def get_ai_models(
    payload: AIProviderDraft,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, list[str]]:
    try:
        models = await list_provider_models(
            base_url=payload.base_url,
            timeout_seconds=payload.timeout_seconds,
            api_key=_draft_api_key(payload, db),
            protocol=payload.protocol,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if payload.provider_id:
        config = db.scalar(select(AIProviderConfig).where(AIProviderConfig.id == payload.provider_id))
        if config:
            config.models_json = json.dumps(models, ensure_ascii=False)
            db.commit()
    return {"models": models}


@app.post("/api/ai/provider/test-draft")
async def test_ai_provider_draft(
    payload: AIProviderDraft,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    if not payload.model:
        raise HTTPException(status_code=422, detail="请先选择模型")
    try:
        result = await test_provider_values(
            base_url=payload.base_url,
            model=payload.model,
            protocol=payload.protocol,
            timeout_seconds=payload.timeout_seconds,
            api_key=_draft_api_key(payload, db),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"result": result}


@app.post("/api/ai/analyze", status_code=201)
async def analyze_with_ai(
    payload: AIAnalyzeRequest,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, payload.account_id, user)
    _consume_usage(db, user, "analysis")
    report_text, snapshot, config, prompt_text = await _generate_ai_report(
        db, payload.account_id, payload.start_date, payload.end_date
    )
    history = AIQueryHistory(
        account_id=payload.account_id,
        provider_id=config.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(history)
    db.flush()
    db.add(
        AIAnalysisReport(
            history_id=history.id,
            account_id=payload.account_id,
            provider_id=config.id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            input_snapshot_json=json.dumps(snapshot, ensure_ascii=False, default=str),
            report_text=report_text,
            prompt_text=prompt_text,
            provider_snapshot_json=json.dumps(
                _provider_payload(config), ensure_ascii=False, default=str
            ),
        )
    )
    write_audit(db, "ai.query.create", user, "ai_query", history.id)
    db.commit()
    return _analysis_response(history, report_text, snapshot)


async def _generate_ai_report(
    db: Session, account_id: int, start_date: date, end_date: date
) -> tuple[str, dict[str, Any], AIProviderConfig, str]:
    config = _active_provider(db, account_id)
    if not config:
        raise HTTPException(status_code=404, detail="尚未配置 AI")
    snapshot = range_summary(db, account_id, start_date, end_date)
    if not snapshot["trend"]:
        raise HTTPException(status_code=422, detail="所选日期没有数据")
    if not range_has_complete_data(snapshot):
        requested_days = (end_date - start_date).days + 1
        raise HTTPException(
            status_code=422,
            detail=(
                f"所选日期范围需要 {requested_days} 天完整数据，当前数据库仅有 "
                f"{snapshot['days_with_data']} 天，请先导入缺少日期的数据后再分析"
            ),
        )
    try:
        report_text = await call_provider(config, snapshot)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return report_text, snapshot, config, SYSTEM_PROMPT + "\n\n" + build_prompt(snapshot)


def _analysis_response(
    history: AIQueryHistory, report_text: str, snapshot: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": history.id,
        "report_text": report_text,
        "snapshot": snapshot,
        "start_date": history.start_date,
        "end_date": history.end_date,
        "created_at": history.created_at,
    }


@app.get("/api/ai/reports")
def list_ai_reports(
    account_id: int,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    _get_account(db, account_id, user)
    rows = db.scalars(
        select(AIQueryHistory)
        .where(AIQueryHistory.account_id == account_id)
        .order_by(AIQueryHistory.created_at.desc())
        .limit(50)
    ).all()
    return [
        {
            "id": row.id,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def _get_ai_history(db: Session, history_id: int) -> AIQueryHistory:
    history = db.get(AIQueryHistory, history_id)
    if not history:
        raise HTTPException(status_code=404, detail="查询记录不存在")
    return history


@app.post("/api/ai/reports/{history_id}/analyze")
async def analyze_ai_history(
    history_id: int,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    history = _get_ai_history(db, history_id)
    _get_account(db, history.account_id, user)
    report = db.scalar(
        select(AIAnalysisReport).where(AIAnalysisReport.history_id == history.id)
    )
    if report:
        report_text = report.report_text
        snapshot = json.loads(report.input_snapshot_json)
    else:
        report_text, snapshot, config, prompt_text = await _generate_ai_report(
            db, history.account_id, history.start_date, history.end_date
        )
        report = AIAnalysisReport(
            history_id=history.id,
            account_id=history.account_id,
            provider_id=config.id,
            start_date=history.start_date,
            end_date=history.end_date,
            input_snapshot_json=json.dumps(snapshot, ensure_ascii=False, default=str),
            report_text=report_text,
            prompt_text=prompt_text,
            provider_snapshot_json=json.dumps(
                _provider_payload(config), ensure_ascii=False, default=str
            ),
        )
        db.add(report)
    write_audit(db, "ai.query.view", user, "ai_query", history.id)
    db.commit()
    return _analysis_response(history, report_text, snapshot)


@app.delete("/api/ai/reports/{history_id}", status_code=204)
def delete_ai_history(
    history_id: int,
    user: CsrfUser,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    history = _get_ai_history(db, history_id)
    _get_account(db, history.account_id, user)
    write_audit(db, "ai.query.delete", user, "ai_query", history.id)
    db.execute(
        AIAnalysisReport.__table__.delete().where(AIAnalysisReport.history_id == history.id)
    )
    db.delete(history)
    db.commit()
    return Response(status_code=204)


@app.post("/api/backups", status_code=201)
def make_backup(
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    path = create_backup()
    write_audit(db, "backup.create", user, "backup", path.name)
    db.commit()
    return {"filename": path.name, "size": path.stat().st_size, "created_at": datetime.now(UTC)}


@app.get("/api/backups")
def list_backups(user: Annotated[User, Depends(require_admin)]) -> list[dict[str, Any]]:
    backup_dir = settings.data_dir / "backups"
    return (
        [
            {
                "filename": path.name,
                "size": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, UTC),
            }
            for path in sorted(
                backup_dir.glob("*.vxbackup"), key=lambda item: item.stat().st_mtime, reverse=True
            )
        ]
        if backup_dir.exists()
        else []
    )


@app.get("/api/backups/{filename}")
def download_backup(filename: str, user: Annotated[User, Depends(require_admin)]) -> FileResponse:
    if Path(filename).name != filename or not filename.endswith(".vxbackup"):
        raise HTTPException(status_code=404, detail="备份不存在")
    path = settings.data_dir / "backups" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="备份不存在")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@app.get("/api/audit")
def audit_logs(
    limit: int = 100,
    user: Annotated[User, Depends(require_admin)] = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500))
    ).all()
    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.get("/api/system/versions")
async def system_versions(
    user: CurrentUser,
    registry: str | None = Query(default=None),
) -> dict[str, Any]:
    selected_registry = registry or settings.update_registry
    if selected_registry not in ALLOWED_REGISTRIES:
        raise HTTPException(status_code=400, detail="不支持的镜像仓库")
    try:
        versions = await fetch_registry_versions(REGISTRY_REPOSITORIES.get(selected_registry, settings.update_repository), selected_registry)
    except UpdateRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return version_payload(versions, selected_registry)


@app.get("/api/system/update-status")
def system_update_status(
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    return read_update_status()


@app.put("/api/system/update-registry")
def system_update_registry(
    payload: SystemRegistryUpdate,
    user: Annotated[User, Depends(require_csrf_admin)],
) -> dict[str, str]:
    if payload.registry not in ALLOWED_REGISTRIES:
        raise HTTPException(status_code=400, detail="不支持的镜像仓库")
    try:
        save_update_registry(payload.registry)
    except UpdateRegistryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"registry": payload.registry}


@app.post("/api/system/update", status_code=202)
async def system_update(
    payload: SystemUpdateRequest,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if not settings.updater_enabled:
        raise HTTPException(status_code=409, detail="当前部署未启用在线更新服务")
    if payload.registry not in ALLOWED_REGISTRIES:
        raise HTTPException(status_code=400, detail="不支持的镜像仓库")
    if version_key(payload.version) == version_key(__version__):
        raise HTTPException(status_code=400, detail="不能更新到当前正在运行的版本")
    try:
        versions = await fetch_registry_versions(REGISTRY_REPOSITORIES.get(payload.registry, settings.update_repository), payload.registry)
    except UpdateRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if payload.version not in {row["version"] for row in versions}:
        raise HTTPException(status_code=404, detail="所选镜像仓库中不存在该版本")
    try:
        backup = create_backup()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新前创建备份失败：{exc}") from exc
    try:
        request = queue_update(payload.version, backup.name, payload.registry)
    except UpdateBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新任务入队失败：{exc}") from exc
    write_audit(
        db,
        "system.update.request",
        user,
        "system_update",
        request["id"],
        {"from": __version__, "to": payload.version, "backup": backup.name},
    )
    db.commit()
    return {
        "id": request["id"],
        "state": "queued",
        "target_version": payload.version,
        "backup_filename": backup.name,
    }


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    class SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
            try:
                response = await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404:
                    raise
                response = None

            if response is not None and response.status_code != 404:
                return response
            request_path = str(scope.get("path", ""))
            if (
                path.startswith("api/")
                or request_path.startswith("/api/")
                or Path(path).suffix
            ):
                if response is not None:
                    return response
                raise HTTPException(status_code=404)
            return await super().get_response("index.html", scope)

    app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")
