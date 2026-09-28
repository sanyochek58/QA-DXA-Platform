"""КОНТРАКТ ML-сервиса. Core и фронтенд завязаны на эти поля.

Внутренности pipeline/ можно менять как угодно, этот файл — только по договорённости команды.
"""

from typing import Literal

from pydantic import BaseModel, Field

Region = Literal["spine", "right_hip", "left_hip", "unknown"]


class AnalyzeRequest(BaseModel):
    study_id: str
    # Пути к DICOM относительно DATA_DIR общего тома, например "studies/<id>/0.dcm"
    files: list[str] = Field(min_length=1)


class ImageResult(BaseModel):
    index: int
    file: str
    region: Region
    region_confidence: float
    preview_path: str | None = None  # PNG с разметкой относительно DATA_DIR
    measurements: dict[str, float] = Field(default_factory=dict)


class Violation(BaseModel):
    code: str = Field(examples=["HIP_ROTATION"])
    region: Region
    severity: Literal["critical", "minor"]
    probability: float = Field(ge=0, le=1)
    threshold: float
    title_ru: str
    message_ru: str
    how_to_fix_ru: str
    evidence: dict[str, float] = Field(default_factory=dict)
    image_indexes: list[int] = Field(default_factory=list)


class RegionResult(BaseModel):
    region: Region
    quality_ok: bool
    probability_bad: float
    threshold: float
    image_indexes: list[int]


class AnalyzeResponse(BaseModel):
    study_id: str
    quality_ok: bool
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    regions: list[RegionResult]
    violations: list[Violation]
    images: list[ImageResult]
    metadata: dict[str, str] = Field(default_factory=dict)
    model_version: str
    processing_ms: int
