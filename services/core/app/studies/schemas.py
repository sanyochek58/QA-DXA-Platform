import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.studies.models import ReviewStatus, StudyStatus


class UserShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class StudyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    title: str | None
    n_images: int
    status: StudyStatus
    quality_ok: bool | None
    needs_review: bool
    violation_codes: list[str]
    review_status: ReviewStatus
    review_quality_ok: bool | None
    uploaded_by: UserShort


class StudyRead(StudyListItem):
    error: str | None
    result: dict[str, Any] | None
    model_version: str | None
    processing_ms: int | None
    finished_at: datetime | None
    file_names: list[str]
    reviewed_by: UserShort | None
    reviewed_at: datetime | None
    review_comment: str | None


class StudyPage(BaseModel):
    items: list[StudyListItem]
    total: int


class ReviewCreate(BaseModel):
    """Решение врача по исследованию."""

    quality_ok: bool
    comment: str | None = Field(default=None, max_length=2000)
