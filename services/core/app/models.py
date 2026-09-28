"""Реестр всех ORM-моделей. Alembic видит только импортированные таблицы:
каждую новую модель добавляй сюда, иначе autogenerate её «не заметит»."""

from app.auth.models import User  # noqa: F401
from app.core.db import Base
from app.studies.models import Study  # noqa: F401

__all__ = ["Base"]
