from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# Пул соединений на всё приложение (как HikariCP). pool_pre_ping проверяет,
# живо ли соединение перед выдачей: переживём перезапуск Postgres без рестарта приложения.
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# Фабрика сессий (как EntityManagerFactory). Каждый вызов SessionLocal() — новая сессия.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Базовый класс для всех таблиц."""


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
