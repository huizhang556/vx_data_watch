from __future__ import annotations

from app.security import decrypt_secret, encrypt_secret, hash_password, verify_password


def test_password_hash_and_secret_encryption() -> None:
    password_hash = hash_password("a-secure-password")
    assert "a-secure-password" not in password_hash
    assert verify_password(password_hash, "a-secure-password")
    assert not verify_password(password_hash, "wrong")

    encrypted = encrypt_secret("sk-test-secret")
    assert b"sk-test-secret" not in encrypted
    assert decrypt_secret(encrypted) == "sk-test-secret"
