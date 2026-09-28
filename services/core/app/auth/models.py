import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Role(enum.StrEnum):
    TECHNOLOGIST = "technologist"  # лаборант: загружает исследования, видит свои
    RADIOLOGIST = "radiologist"  # врач: очередь на проверку, подтверждает вердикты
    ADMIN = "admin"  # заведующий + администратор: дашборд, пользователи


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda x: [e.value for e in x])
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Связка с Госуслугами: сотрудника находим по СНИЛС, при первом входе запоминаем oid ЕСИА
    snils: Mapped[str | None] = mapped_column(String(11), unique=True)
    esia_oid: Mapped[str | None] = mapped_column(String(64), unique=True)
