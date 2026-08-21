from __future__ import annotations

import hashlib
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import httpx
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import User, VerificationCode


def normalize_email(value: str) -> str:
    return value.strip().lower()


def require_captcha(request: Request, token: str | None) -> None:
    settings = get_settings()
    if not settings.captcha_enabled:
        return
    if not token or not settings.captcha_secret_key:
        raise HTTPException(status_code=400, detail="请完成安全验证")
    if settings.captcha_provider != "turnstile":
        raise HTTPException(status_code=503, detail="当前人机验证服务暂不支持")
    try:
        response = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": settings.captcha_secret_key, "response": token,
                  "remoteip": request.client.host if request.client else ""},
            timeout=10,
        )
        response.raise_for_status()
        if not response.json().get("success"):
            raise ValueError("verification failed")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="人机验证失败，请重试") from exc


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def send_code(db: Session, email: str, purpose: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise HTTPException(status_code=503, detail="系统尚未配置 SMTP，暂时无法发送验证码")
    now = datetime.now(UTC)
    recent = db.scalar(select(VerificationCode).where(
        VerificationCode.email == email,
        VerificationCode.purpose == purpose,
        VerificationCode.created_at >= now - timedelta(minutes=1),
    ))
    if recent:
        raise HTTPException(status_code=429, detail="验证码发送过于频繁，请稍后再试")
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(VerificationCode(email=email, purpose=purpose, code_hash=_code_hash(code),
                            expires_at=now + timedelta(minutes=settings.verification_code_minutes)))
    message = EmailMessage()
    message["Subject"] = "VX Data Watch 验证码"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(f"您的验证码是：{code}\n验证码 {settings.verification_code_minutes} 分钟内有效，请勿向他人泄露。")
    try:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_starttls and not settings.smtp_ssl:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="验证码邮件发送失败，请检查 SMTP 配置") from exc


def consume_code(db: Session, email: str, purpose: str, code: str) -> bool:
    row = db.scalar(select(VerificationCode).where(
        VerificationCode.email == email, VerificationCode.purpose == purpose,
        VerificationCode.consumed_at.is_(None),
    ).order_by(VerificationCode.created_at.desc()))
    if not row or row.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        return False
    if not secrets.compare_digest(row.code_hash, _code_hash(code)):
        return False
    row.consumed_at = datetime.now(UTC)
    return True


def email_user(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))
