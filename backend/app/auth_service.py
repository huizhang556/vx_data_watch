from __future__ import annotations

import hashlib
import json
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import httpx
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AppSetting, User, VerificationCode
from .security import decrypt_secret, encrypt_secret


def normalize_email(value: str) -> str:
    return value.strip().lower()


def auth_settings(db: Session) -> dict[str, object]:
    row = db.scalar(select(AppSetting).where(AppSetting.key == "auth"))
    defaults = get_settings()
    values: dict[str, object] = {
        "registration_enabled": defaults.registration_enabled,
        "smtp_host": defaults.smtp_host,
        "smtp_port": defaults.smtp_port,
        "smtp_username": defaults.smtp_username,
        "smtp_password": defaults.smtp_password,
        "smtp_from": defaults.smtp_from,
        "smtp_starttls": defaults.smtp_starttls,
        "smtp_ssl": defaults.smtp_ssl,
        "verification_code_minutes": defaults.verification_code_minutes,
        "captcha_enabled": defaults.captcha_enabled,
        "captcha_provider": defaults.captcha_provider,
        "captcha_site_key": defaults.captcha_site_key,
        "captcha_secret_key": defaults.captcha_secret_key,
    }
    if row:
        try:
            values.update(json.loads(decrypt_secret(row.value)))
        except (ValueError, TypeError):
            pass
    return values


def save_auth_settings(db: Session, values: dict[str, object]) -> None:
    row = db.scalar(select(AppSetting).where(AppSetting.key == "auth"))
    encrypted = encrypt_secret(json.dumps(values, ensure_ascii=False))
    if row:
        row.value = encrypted
    else:
        db.add(AppSetting(key="auth", value=encrypted))


def require_captcha(request: Request, token: str | None, db: Session | None = None) -> None:
    settings = auth_settings(db) if db is not None else get_settings().__dict__
    if not settings.get("captcha_enabled"):
        return
    if not token or not settings.get("captcha_secret_key"):
        raise HTTPException(status_code=400, detail="请完成安全验证")
    if settings.get("captcha_provider") != "turnstile":
        raise HTTPException(status_code=503, detail="当前人机验证服务暂不支持")
    try:
        response = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": str(settings.get("captcha_secret_key")), "response": token,
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
    settings = auth_settings(db)
    if not settings.get("smtp_host") or not settings.get("smtp_from"):
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
        expires_at=now + timedelta(minutes=int(settings["verification_code_minutes"]))))
    message = EmailMessage()
    message["Subject"] = "VX Data Watch 验证码"
    message["From"] = str(settings["smtp_from"])
    message["To"] = email
    message.set_content(f"您的验证码是：{code}\n验证码 {settings['verification_code_minutes']} 分钟内有效，请勿向他人泄露。")
    try:
        smtp_class = smtplib.SMTP_SSL if settings["smtp_ssl"] else smtplib.SMTP
        with smtp_class(str(settings["smtp_host"]), int(settings["smtp_port"]), timeout=15) as smtp:
            if settings["smtp_starttls"] and not settings["smtp_ssl"]:
                smtp.starttls()
            if settings["smtp_username"]:
                smtp.login(str(settings["smtp_username"]), str(settings["smtp_password"] or ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="验证码邮件发送失败，请检查 SMTP 配置") from exc


def test_smtp_connection(db: Session, recipient: str) -> None:
    settings = auth_settings(db)
    if not settings.get("smtp_host") or not settings.get("smtp_from"):
        raise HTTPException(status_code=422, detail="请先填写 SMTP 服务器和发件人地址")
    message = EmailMessage()
    message["Subject"] = "VX Data Watch SMTP 测试邮件"
    message["From"] = str(settings["smtp_from"])
    message["To"] = recipient.strip()
    message.set_content("这是一封 VX Data Watch 测试邮件。收到此邮件表示 SMTP 配置正确。")
    try:
        smtp_class = smtplib.SMTP_SSL if settings["smtp_ssl"] else smtplib.SMTP
        with smtp_class(str(settings["smtp_host"]), int(settings["smtp_port"]), timeout=15) as smtp:
            if settings["smtp_starttls"] and not settings["smtp_ssl"]:
                smtp.starttls()
            if settings["smtp_username"]:
                smtp.login(str(settings["smtp_username"]), str(settings["smtp_password"] or ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(status_code=502, detail=f"SMTP 连接或发信失败：{exc}") from exc


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
