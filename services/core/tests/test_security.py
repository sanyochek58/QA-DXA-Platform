import jwt
import pytest

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h.startswith("$argon2")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)
    assert hash_password("secret123") != h  # соль разная у каждого хеша


def test_token_roundtrip():
    payload = decode_access_token(create_access_token("user-id", "admin"))
    assert payload["sub"] == "user-id" and payload["role"] == "admin"


def test_tampered_token_rejected():
    header, _, signature = create_access_token("user-id", "technologist").split(".")
    forged = jwt.encode({"sub": "user-id", "role": "admin"}, "other-secret-" + "y" * 40, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(f"{header}.{forged.split('.')[1]}.{signature}")
