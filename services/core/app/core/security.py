"""Пароли и JWT. Чистые функции без FastAPI — их легко тестировать.

Пароли: argon2 через pwdlib (медленный алгоритм специально, соль встроена в хеш).
JWT: PyJWT, HS256 — один общий секрет из .env.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_password_hash = PasswordHash.recommended()

# Хеш-«пустышка»: проверяем пароль даже когда пользователя нет,
# чтобы время ответа не выдавало, существует ли такой email (timing attack).
DUMMY_HASH = _password_hash.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,  # id пользователя
        "role": role,  # удобно фронту; права на бэке всё равно проверяем по БД
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Бросает jwt.InvalidTokenError, если подпись неверна или срок истёк."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
