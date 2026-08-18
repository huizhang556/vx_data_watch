from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

from .models import Role


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=10, max_length=200)
    role: Role = Role.viewer


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class UserResponse(BaseModel):
    id: int
    username: str
    role: Role
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
    protocol: Literal["chat_completions", "responses"] = "chat_completions"
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
    protocol: Literal["chat_completions", "responses"] = "chat_completions"
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
