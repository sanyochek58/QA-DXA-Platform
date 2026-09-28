"""DTO авторизации и пользователей. Модель БД наружу не отдаём никогда:
UserRead просто не содержит password_hash, поэтому утечь ему неоткуда."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.auth.esia import snils as snils_lib
from app.auth.models import Role


def _snils(v: str | None) -> str | None:
    if v is None or not str(v).strip():
        return None
    try:
        return snils_lib.normalize(v)
    except snils_lib.InvalidSnilsError as e:
        raise ValueError(str(e)) from e


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Role
    snils: str | None = None

    _check_snils = field_validator("snils", mode="before")(_snils)


class UserUpdate(BaseModel):
    """Частичное обновление: передаются только нужные поля."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    snils: str | None = None

    _check_snils = field_validator("snils", mode="before")(_snils)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    snils: str | None
    esia_linked: bool = False

    @classmethod
    def from_user(cls, user) -> "UserRead":
        obj = cls.model_validate(user)
        obj.esia_linked = user.esia_oid is not None
        return obj


class EsiaConfig(BaseModel):
    enabled: bool
    mode: str


class EsiaStart(BaseModel):
    url: str
    state: str


class EsiaCallback(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=4096)
    redirect_uri: str = Field(max_length=512)


class MockEsiaPerson(BaseModel):
    full_name: str
    snils: str
    email: str | None
    phone: str | None


class MockEsiaLogin(BaseModel):
    login: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    redirect_uri: str = Field(max_length=512)
    state: str = Field(max_length=4096)


class MockEsiaRedirect(BaseModel):
    redirect: str
