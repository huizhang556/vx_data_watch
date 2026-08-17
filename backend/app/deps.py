from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import LoginSession, Role, User
from .security import token_hash

Db = Annotated[Session, Depends(get_db)]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def get_session_and_user(request: Request, db: Db) -> tuple[LoginSession, User]:
    raw_token = request.cookies.get("vx_session")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    login_session = db.scalar(
        select(LoginSession).where(LoginSession.token_hash == token_hash(raw_token))
    )
    if not login_session or _aware(login_session.expires_at) <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已过期")
    user = db.get(User, login_session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不可用")
    return login_session, user


def get_current_user(request: Request, db: Db) -> User:
    return get_session_and_user(request, db)[1]


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_editor(user: CurrentUser) -> User:
    if user.role not in {Role.admin, Role.editor}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要编辑权限")
    return user


def require_admin(user: CurrentUser) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def require_csrf(
    request: Request,
    db: Db,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> User:
    login_session, user = get_session_and_user(request, db)
    if not x_csrf_token or not hmac.compare_digest(x_csrf_token, login_session.csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF 校验失败")
    return user


CsrfUser = Annotated[User, Depends(require_csrf)]


def require_csrf_editor(user: CsrfUser) -> User:
    if user.role not in {Role.admin, Role.editor}:
        raise HTTPException(status_code=403, detail="需要编辑权限")
    return user


def require_csrf_admin(user: CsrfUser) -> User:
    if user.role != Role.admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
