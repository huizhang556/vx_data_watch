from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from .models import Role


def validate_password_strength(value: str | None) -> str | None:
    if value is not None and (len(value) < 10 or not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value)):
        raise ValueError("密码至少 10 位，并同时包含字母和数字")
    return value


def validate_email_address(value: str | None) -> str | None:
    if value is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()):
        raise ValueError("请输入有效的邮箱地址")
    return value


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=200)

    _password_strength = field_validator("password")(validate_password_strength)


class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_token: str | None = None


class RegisterCodeRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    captcha_token: str | None = None

    _email_format = field_validator("email")(validate_email_address)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=200)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    captcha_token: str | None = None

    _password_strength = field_validator("password")(validate_password_strength)
    _email_format = field_validator("email")(validate_email_address)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    captcha_token: str | None = None

    _email_format = field_validator("email")(validate_email_address)


class PasswordResetConfirm(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=10, max_length=200)
    captcha_token: str | None = None

    _password_strength = field_validator("new_password")(validate_password_strength)
    _email_format = field_validator("email")(validate_email_address)


class AuthSettingsUpdate(BaseModel):
    registration_enabled: bool = False
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, max_length=254)
    smtp_password: str | None = Field(default=None, max_length=500)
    smtp_from: str | None = Field(default=None, max_length=254)
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    verification_code_minutes: int = Field(default=10, ge=1, le=60)
    captcha_enabled: bool = False
    captcha_provider: str = Field(default="turnstile", max_length=30)
    captcha_site_key: str | None = Field(default=None, max_length=500)
    captcha_secret_key: str | None = Field(default=None, max_length=500)

    @field_validator("smtp_from")
    @classmethod
    def validate_sender(cls, value: str | None) -> str | None:
        if value and "<" in value and ">" in value:
            address = value[value.rfind("<") + 1:value.rfind(">")]
            validate_email_address(address)
            return value
        return validate_email_address(value)


class SMTPTestRequest(BaseModel):
    recipient: str = Field(min_length=5, max_length=254)

    _email_format = field_validator("recipient")(validate_email_address)


class UsernameChange(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=200)
    role: Role = Role.viewer
    level: int = Field(default=0, ge=0, le=3)
    avatar: str | None = Field(default=None, max_length=2_000_000)

    _password_strength = field_validator("password")(validate_password_strength)
    _email_format = field_validator("email")(validate_email_address)


class UserAdminUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=254)
    password: str | None = Field(default=None, min_length=10, max_length=200)
    role: Role | None = None
    level: int | None = Field(default=None, ge=0, le=3)
    is_active: bool | None = None
    avatar: str | None = Field(default=None, max_length=2_000_000)

    _password_strength = field_validator("password")(validate_password_strength)
    _email_format = field_validator("email")(validate_email_address)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)

    _password_strength = field_validator("new_password")(validate_password_strength)


class UserResponse(BaseModel):
    id: int
    username: str
    role: Role
    level: int
    csrf_token: str | None = None


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class AccountResponse(AccountCreate):
    id: int
    created_at: datetime


class VideoMetricInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    published_at: datetime | None = None
    metric_date: date
    plays: int = Field(ge=0)
    cumulative_plays: int | None = Field(default=None, ge=0)
    cumulative_plays_approximate: bool = False
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    identity_key: str | None = Field(default=None, max_length=180)


class VideoMetricCommit(BaseModel):
    account_id: int
    metric_date: date | None = None
    filename: str | None = None
    rows: list[VideoMetricInput] = Field(min_length=1, max_length=1000)


class AIProviderInput(BaseModel):
    account_id: int
    provider_id: int | None = None
    name: str = Field(default="默认 AI", max_length=100)
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    protocol: Literal["chat_completions", "responses", "anthropic", "gemini", "grok"] = "chat_completions"
    api_key: str | None = Field(default=None, max_length=500)
    timeout_seconds: int = Field(default=60, ge=5, le=300)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = HttpUrl(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Base URL must use http or https")
        return value.rstrip("/")


class AIProviderDraft(BaseModel):
    account_id: int
    provider_id: int | None = None
    base_url: str = Field(min_length=8, max_length=500)
    model: str | None = Field(default=None, max_length=200)
    protocol: Literal["chat_completions", "responses", "anthropic", "gemini", "grok"] = "chat_completions"
    api_key: str | None = Field(default=None, max_length=500)
    timeout_seconds: int = Field(default=60, ge=5, le=300)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parsed = HttpUrl(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Base URL must use http or https")
        return value.rstrip("/")


class AIProviderSelect(BaseModel):
    account_id: int
    provider_id: int


class AIQuickConfigInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider_id: int
    model: str = Field(min_length=1, max_length=200)


class AIChatCategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int | None = Field(default=None, ge=0)
    pinned: bool | None = None
    provider_id: int | None = None


class AIChatSessionInput(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=200)
    category_id: int | None = None
    provider_id: int | None = None


class AIChatSessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    category_id: int | None = None
    pinned: bool | None = None
    provider_id: int | None = None


class AIChatMessageInput(BaseModel):
    content: str = Field(default="", max_length=100_000)
    provider_id: int | None = None
    attachments: list[dict[str, str]] = Field(default_factory=list, max_length=8)


class AIAnalyzeRequest(BaseModel):
    account_id: int
    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def validate_range(cls, value: date, info: Any) -> date:
        start = info.data.get("start_date")
        if start and value < start:
            raise ValueError("end_date must not be earlier than start_date")
        if start and (value - start).days > 366:
            raise ValueError("date range cannot exceed 366 days")
        return value


class AIQueryHistoryUpdate(BaseModel):
    start_date: date
    end_date: date

    @field_validator("end_date")
    @classmethod
    def validate_range(cls, value: date, info: Any) -> date:
        start = info.data.get("start_date")
        if start and value < start:
            raise ValueError("end_date must not be earlier than start_date")
        if start and (value - start).days > 366:
            raise ValueError("date range cannot exceed 366 days")
        return value


class SystemUpdateRequest(BaseModel):
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=30)
    registry: str = Field(default="docker.io", pattern=r"^[a-z0-9.-]+(?::\d+)?$", max_length=255)


class SystemRegistryUpdate(BaseModel):
    registry: str = Field(pattern=r"^[a-z0-9.-]+(?::\d+)?$", max_length=255)


class DownloadSettings(BaseModel):
    quality: Literal["best", "2160", "1440", "1080", "720", "480", "360"] = "1080"
    download_type: Literal["video_audio", "video", "audio"] = "video_audio"
    save_thumbnail: bool = True
    transcode_enabled: bool = False
    transcode_quality: Literal["fast", "balanced", "high"] = "balanced"
    keep_original: bool = True
    cookies_enabled: bool = True
    proxy_enabled: bool = False
    proxy_url: str | None = Field(default=None, max_length=500)
    proxy_auto_check: bool = True
    output_dir: str = Field(default="downloads", min_length=1, max_length=500)
    cookies: str | None = Field(default=None, max_length=2_000_000)


class DownloadCookieTest(BaseModel):
    cookies: str = Field(default="", max_length=2_000_000)


class DownloadProxyTest(BaseModel):
    proxy_url: str = Field(min_length=8, max_length=500)


class DownloadTaskCreate(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)
