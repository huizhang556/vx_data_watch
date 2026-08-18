from __future__ import annotations

import json
import time
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
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.responses import Response as FastAPIResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
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
)
from .analytics import date_summary, range_has_complete_data, range_summary, range_video_summary
from .audit import write_audit
from .backups import create_backup
from .config import get_settings
from .database import get_db, init_db
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
    AuditLog,
    ChannelsAccount,
    DailyAccountMetric,
    DailyAccountMetricRevision,
    DailyVideoMetric,
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
    AIAnalyzeRequest,
    AIProviderDraft,
    AIProviderInput,
    AIProviderSelect,
    LoginRequest,
    PasswordChange,
    SetupRequest,
    SystemUpdateRequest,
    UserCreate,
    VideoMetricCommit,
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
    UpdateBusyError,
    UpdateRegistryError,
    fetch_registry_versions,
    queue_update,
    read_update_status,
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
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
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
        "role": user.role.value,
        "csrf_token": csrf_token,
    }


def _read_upload(file: UploadFile) -> bytes:
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"文件不能超过 {settings.max_upload_mb} MB")
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")
    return content


def _get_account(db: Session, account_id: int) -> ChannelsAccount:
    account = db.get(ChannelsAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="视频号账号不存在")
    return account


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/api/setup/status")
def setup_status(db: Annotated[Session, Depends(get_db)]) -> dict[str, bool]:
    return {"initialized": (db.scalar(select(func.count(User.id))) or 0) > 0}


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
        username=payload.username, password_hash=hash_password(payload.password), role=Role.admin
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
    attempt_key = (
        f"{request.client.host if request.client else 'unknown'}:{payload.username.lower()}"
    )
    now = time.monotonic()
    attempts = [value for value in _login_attempts.get(attempt_key, []) if now - value < 300]
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请 5 分钟后重试")
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not user.is_active or not verify_password(user.password_hash, payload.password):
        attempts.append(now)
        _login_attempts[attempt_key] = attempts
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    _login_attempts.pop(attempt_key, None)
    raw_token, login_session = _create_session(db, user, request)
    write_audit(db, "auth.login", user, "session")
    db.commit()
    _set_session_cookie(request, response, raw_token)
    return _user_payload(user, login_session.csrf_token)


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
            "is_active": row.is_active,
            "created_at": row.created_at,
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
    created = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(created)
    db.flush()
    write_audit(db, "user.create", user, "user", created.id, {"role": created.role.value})
    db.commit()
    return {"id": created.id, "username": created.username, "role": created.role.value}


@app.get("/api/accounts")
def list_accounts(
    user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> list[dict[str, Any]]:
    rows = db.scalars(select(ChannelsAccount).order_by(ChannelsAccount.created_at)).all()
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
    user: Annotated[User, Depends(require_csrf_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if db.scalar(select(ChannelsAccount).where(ChannelsAccount.name == payload.name.strip())):
        raise HTTPException(status_code=409, detail="账号名称已存在")
    account = ChannelsAccount(name=payload.name.strip(), description=payload.description)
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
    _get_account(db, account_id)
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
    _get_account(db, account_id)
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
    _get_account(db, account_id)
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
    _get_account(db, payload.account_id)
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
    _get_account(db, account_id)
    return date_summary(db, account_id, metric_date)


@app.get("/api/analytics/range")
def range_analytics(
    account_id: int,
    start_date: date,
    end_date: date,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, account_id)
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
    _get_account(db, account_id)
    if end_date < start_date or (end_date - start_date).days > 366:
        raise HTTPException(status_code=422, detail="日期范围无效或超过 366 天")
    return range_video_summary(db, account_id, start_date, end_date)


def _provider_payload(config: AIProviderConfig) -> dict[str, Any]:
    return {
        "id": config.id,
        "account_id": config.account_id,
        "name": config.name,
        "base_url": config.base_url,
        "model": config.model,
        "protocol": config.protocol,
        "timeout_seconds": config.timeout_seconds,
        "api_key_configured": bool(config.encrypted_api_key),
        "is_active": config.is_active,
    }


def _provider_candidates(db: Session, account_id: int) -> list[AIProviderConfig]:
    _get_account(db, account_id)
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


def _active_provider(db: Session, account_id: int) -> AIProviderConfig | None:
    rows = _provider_candidates(db, account_id)
    return next((row for row in rows if row.account_id == account_id and row.is_active), None) or next(
        (row for row in rows if row.account_id is None and row.is_active), None
    )


@app.get("/api/ai/providers")
def list_ai_providers(
    account_id: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> list[dict[str, Any]]:
    return [_provider_payload(row) for row in _provider_candidates(db, account_id)]


@app.get("/api/ai/provider")
def get_ai_provider(
    account_id: int, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> dict[str, Any] | None:
    config = _active_provider(db, account_id)
    return _provider_payload(config) if config else None


@app.put("/api/ai/provider")
def save_ai_provider(
    payload: AIProviderInput,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, payload.account_id)
    config = None
    if payload.provider_id:
        config = db.scalar(
            select(AIProviderConfig).where(
                AIProviderConfig.id == payload.provider_id,
                (AIProviderConfig.account_id == payload.account_id)
                | (AIProviderConfig.account_id.is_(None)),
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
            account_id=payload.account_id,
        )
        db.add(config)
    elif config.account_id is None:
        config.account_id = payload.account_id
    config.name = payload.name
    config.base_url = payload.base_url
    config.model = payload.model
    config.protocol = payload.protocol
    config.timeout_seconds = payload.timeout_seconds
    db.execute(
        AIProviderConfig.__table__.update()
        .where(AIProviderConfig.account_id == payload.account_id)
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
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, payload.account_id)
    config = db.scalar(
        select(AIProviderConfig).where(
            AIProviderConfig.id == payload.provider_id,
            (AIProviderConfig.account_id == payload.account_id)
            | (AIProviderConfig.account_id.is_(None)),
        )
    )
    if not config:
        raise HTTPException(status_code=404, detail="接口配置不存在")
    if config.account_id is None:
        config.account_id = payload.account_id
    db.execute(
        AIProviderConfig.__table__.update()
        .where(AIProviderConfig.account_id == payload.account_id)
        .values(is_active=False)
    )
    config.is_active = True
    write_audit(db, "ai.provider.select", user, "ai_provider", config.id)
    db.commit()
    return _provider_payload(config)


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
                (AIProviderConfig.account_id == payload.account_id)
                | (AIProviderConfig.account_id.is_(None)),
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
                (AIProviderConfig.account_id == payload.account_id)
                | (AIProviderConfig.account_id.is_(None)),
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
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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
    user: Annotated[User, Depends(require_csrf_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    _get_account(db, payload.account_id)
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
    user: Annotated[User, Depends(require_csrf_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    history = _get_ai_history(db, history_id)
    _get_account(db, history.account_id)
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
    user: Annotated[User, Depends(require_csrf_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    history = _get_ai_history(db, history_id)
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
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    try:
        versions = await fetch_registry_versions(settings.update_repository)
    except UpdateRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return version_payload(versions)


@app.get("/api/system/update-status")
def system_update_status(
    user: Annotated[User, Depends(require_admin)],
) -> dict[str, Any]:
    return read_update_status()


@app.post("/api/system/update", status_code=202)
async def system_update(
    payload: SystemUpdateRequest,
    user: Annotated[User, Depends(require_csrf_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    if not settings.updater_enabled:
        raise HTTPException(status_code=409, detail="当前部署未启用在线更新服务")
    if version_key(payload.version) == version_key(__version__):
        raise HTTPException(status_code=400, detail="不能更新到当前正在运行的版本")
    try:
        versions = await fetch_registry_versions(settings.update_repository)
    except UpdateRegistryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if payload.version not in {row["version"] for row in versions}:
        raise HTTPException(status_code=404, detail="Docker Hub 中不存在该版本")
    try:
        backup = create_backup()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"更新前创建备份失败：{exc}") from exc
    try:
        request = queue_update(payload.version, backup.name)
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
