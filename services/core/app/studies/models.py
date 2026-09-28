import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.core.db import Base

# JSONB в Postgres, обычный JSON в других БД (на случай тестов на SQLite)
JsonType = JSON().with_variant(JSONB(), "postgresql")


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda x: [e.value for e in x])


class StudyStatus(enum.StrEnum):
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ReviewStatus(enum.StrEnum):
    NOT_REQUIRED = "not_required"  # модель уверена, врачу не нужно
    PENDING = "pending"  # ждёт врача
    CONFIRMED = "confirmed"  # врач согласился с системой
    CORRECTED = "corrected"  # врач исправил вердикт


class Study(Base):
    __tablename__ = "studies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    file_names: Mapped[list[str]] = mapped_column(JsonType, default=list)
    n_images: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[StudyStatus] = mapped_column(
        _enum(StudyStatus, "study_status"), default=StudyStatus.PROCESSING
    )
    error: Mapped[str | None] = mapped_column(Text)
    quality_ok: Mapped[bool | None]
    needs_review: Mapped[bool] = mapped_column(default=False)
    violation_codes: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonType)
    model_version: Mapped[str | None] = mapped_column(String(64))
    processing_ms: Mapped[int | None]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    review_status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "review_status"), default=ReviewStatus.NOT_REQUIRED, index=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_quality_ok: Mapped[bool | None]
    review_comment: Mapped[str | None] = mapped_column(Text)

    # lazy="selectin": автор подгружается отдельным запросом сразу, а не лениво при обращении
    # (ленивая подгрузка в async-коде падает с MissingGreenlet)
    uploaded_by: Mapped[User] = relationship(foreign_keys=[uploaded_by_id], lazy="selectin")
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id], lazy="selectin")
