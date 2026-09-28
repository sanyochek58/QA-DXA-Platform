"""Тестовые сотрудники. Скрипт идемпотентный: повторный запуск ничего не дублирует,
но дописывает СНИЛС тем, у кого его ещё нет (для входа через Госуслуги).

СНИЛС совпадают с тестовыми учётками mock-ЕСИА (app/auth/esia/provider.py → MOCK_PERSONS).
Полная таблица логинов — в README.md, раздел «Тестовые данные».

Запуск: uv run python -m app.scripts.seed
"""

import asyncio

from app.auth import service
from app.auth.esia import snils as snils_lib
from app.auth.models import Role
from app.auth.schemas import UserCreate
from app.core.db import SessionLocal, engine

DEMO_USERS: list[tuple[UserCreate, bool]] = [
    # (данные, активен)
    (
        UserCreate(
            email="lab@dxa-qa.ru",
            full_name="Ирина Садыкова",
            password="lab12345",
            role=Role.TECHNOLOGIST,
            snils=snils_lib.make("112233445"),
        ),
        True,
    ),
    (
        UserCreate(
            email="lab2@dxa-qa.ru",
            full_name="Олег Веретенников",
            password="lab12345",
            role=Role.TECHNOLOGIST,
            snils=snils_lib.make("156782394"),
        ),
        True,
    ),
    (
        UserCreate(
            email="doctor@dxa-qa.ru",
            full_name="Мария Лебедева",
            password="doctor12345",
            role=Role.RADIOLOGIST,
            snils=snils_lib.make("200300400"),
        ),
        True,
    ),
    (
        UserCreate(
            email="admin@dxa-qa.ru",
            full_name="Андрей Корнилов",
            password="admin12345",
            role=Role.ADMIN,
            snils=snils_lib.make("301402503"),
        ),
        True,
    ),
    # Заблокированный сотрудник: проверка, что вход через Госуслуги тоже закрыт
    (
        UserCreate(
            email="blocked@dxa-qa.ru",
            full_name="Елена Григорьева",
            password="blocked12345",
            role=Role.TECHNOLOGIST,
            snils=snils_lib.make("412503604"),
        ),
        False,
    ),
    # Смирнов Павел (СНИЛС 523-604-705 59) есть в ЕСИА, но не заведён в системе — вход отклоняется
]


async def main() -> None:
    async with SessionLocal() as session:
        for data, active in DEMO_USERS:
            user = await service.get_by_email(session, str(data.email))
            if user is None:
                user = await service.create_user(session, data)
                print(f"+ {data.email} ({data.role.value})")
            else:
                print(f"= {data.email} уже есть")
            changed = False
            if user.snils is None and data.snils:
                user.snils = data.snils
                changed = True
            if user.is_active != active:
                user.is_active = active
                changed = True
            if changed:
                await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
