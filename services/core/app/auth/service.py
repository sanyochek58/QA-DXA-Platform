"""Бизнес-логика пользователей. Про HTTP не знает: бросает свои исключения,
а роутер переводит их в коды ответа."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.schemas import UserCreate, UserUpdate
from app.core.security import DUMMY_HASH, hash_password, verify_password


class EmailAlreadyExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class SnilsAlreadyExistsError(Exception):
    pass


class EsiaUserNotRegisteredError(Exception):
    """Человек вошёл в Госуслуги, но сотрудника с таким СНИЛС в системе нет."""


class UserBlockedError(Exception):
    pass


async def get_by_snils(session: AsyncSession, snils: str) -> User | None:
    result = await session.execute(select(User).where(User.snils == snils))
    return result.scalar_one_or_none()


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.strip().lower()))
    return result.scalar_one_or_none()


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_by_email(session, email)
    if user is None:
        verify_password(password, DUMMY_HASH)  # то же время ответа, что и для существующего email
        return None
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    return user


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    email = str(data.email).strip().lower()
    if await get_by_email(session, email):
        raise EmailAlreadyExistsError(email)
    if data.snils and await get_by_snils(session, data.snils):
        raise SnilsAlreadyExistsError(data.snils)
    user = User(
        snils=data.snils,
        email=email,
        full_name=data.full_name.strip(),
        password_hash=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)  # подтянуть created_at, который заполнил Postgres
    return user


async def update_user(session: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFoundError(str(user_id))
    # exclude_unset: меняем только то, что клиент реально прислал
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "snils":
            if value and value != user.snils and await get_by_snils(session, value):
                raise SnilsAlreadyExistsError(value)
            if value != user.snils:
                user.esia_oid = None  # СНИЛС сменили — старая привязка к Госуслугам больше не действует
            user.snils = value
        elif field == "password":
            user.password_hash = hash_password(value)
        else:
            setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return user


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def login_via_esia(session: AsyncSession, oid: str, snils: str) -> User:
    """Ищем сотрудника сначала по oid ЕСИА (уже входил), затем по СНИЛС (первый вход)."""
    result = await session.execute(select(User).where(User.esia_oid == oid))
    user = result.scalar_one_or_none() or await get_by_snils(session, snils)
    if user is None:
        raise EsiaUserNotRegisteredError(snils)
    if not user.is_active:
        raise UserBlockedError(str(user.id))
    user.esia_oid = oid
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    return user
