from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import get_settings

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def new_token(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(hours=get_settings().session_hours)


def _load_master_key() -> bytes:
    settings = get_settings()
    if settings.master_key:
        key = base64.urlsafe_b64decode(settings.master_key.encode("ascii"))
        if len(key) != 32:
            raise RuntimeError("VX_MASTER_KEY must decode to exactly 32 bytes")
        return key

    key_path = Path(settings.data_dir) / ".master-key"
    if key_path.exists():
        key = base64.urlsafe_b64decode(key_path.read_text(encoding="ascii").strip())
        if len(key) != 32:
            raise RuntimeError("Invalid data/.master-key")
        return key

    key = AESGCM.generate_key(bit_length=256)
    key_path.write_text(base64.urlsafe_b64encode(key).decode("ascii"), encoding="ascii")
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key


def encrypt_secret(value: str) -> bytes:
    return encrypt_bytes(value.encode("utf-8"), b"vx-data:v1")


def encrypt_bytes(value: bytes, aad: bytes = b"vx-data:backup:v1") -> bytes:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_load_master_key()).encrypt(nonce, value, aad)
    return b"VX1" + nonce + ciphertext


def decrypt_secret(value: bytes) -> str:
    return decrypt_bytes(value, b"vx-data:v1").decode("utf-8")


def decrypt_bytes(value: bytes, aad: bytes = b"vx-data:backup:v1") -> bytes:
    if not value.startswith(b"VX1") or len(value) < 32:
        raise ValueError("Unsupported encrypted secret format")
    return AESGCM(_load_master_key()).decrypt(value[3:15], value[15:], aad)
