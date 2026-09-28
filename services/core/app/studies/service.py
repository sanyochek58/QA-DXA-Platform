"""Логика исследований: сохранить файлы, отдать на анализ, записать вердикт, принять решение врача."""

import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Role, User
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.studies.ml_client import MLClient, MLServiceError
from app.studies.models import ReviewStatus, Study, StudyStatus

log = logging.getLogger(__name__)

CHUNK = 1024 * 1024


class InvalidUploadError(Exception):
    pass


class StudyNotFoundError(Exception):
    pass


def study_dir(study_id: uuid.UUID) -> Path:
    return get_settings().data_dir / "studies" / str(study_id)


async def _save_upload(upload: UploadFile, dest: Path, max_bytes: int) -> None:
    """Пишем файл на диск кусками, не читая целиком в память, и проверяем, что это DICOM."""
    size = 0
    head = b""
    with dest.open("wb") as out:
        while chunk := await upload.read(CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise InvalidUploadError(f"Файл {upload.filename} больше {max_bytes // CHUNK} МБ")
            if len(head) < 132:
                head += chunk[: 132 - len(head)]
            out.write(chunk)
    # Стандартный DICOM-файл: 128 байт преамбулы, затем сигнатура «DICM»
    if len(head) < 132 or head[128:132] != b"DICM":
        raise InvalidUploadError(f"Файл {upload.filename} не похож на DICOM")


async def create_study(
    session: AsyncSession, user: User, files: list[UploadFile], title: str | None
) -> Study:
    if not files:
        raise InvalidUploadError("Не выбрано ни одного файла")
    if len(files) > 40:
        raise InvalidUploadError("Слишком много файлов в одном исследовании (максимум 40)")
    settings = get_settings()
    study = Study(
        uploaded_by_id=user.id,
        title=(title or "").strip() or None,
        # исходные имена файлов не храним: в них бывают ФИО или номер карты пациента
        file_names=[f"image_{i + 1}.dcm" for i in range(len(files))],
        n_images=len(files),
    )
    session.add(study)
    await session.flush()  # получили id, но ещё не закоммитили

    target = study_dir(study.id)
    target.mkdir(parents=True, exist_ok=True)
    try:
        for i, f in enumerate(files):
            await _save_upload(f, target / f"{i}.dcm", settings.max_upload_mb * CHUNK)
    except InvalidUploadError:
        await session.rollback()
        shutil.rmtree(target, ignore_errors=True)
        raise
    await session.commit()
    await session.refresh(study)
    return study


async def process_study(study_id: uuid.UUID, ml: MLClient) -> None:
    """Фоновая задача: отправить файлы в ML и записать результат.

    Работает в своей сессии: сессия HTTP-запроса к этому моменту уже закрыта.
    """
    async with SessionLocal() as session:
        study = await session.get(Study, study_id)
        if study is None:
            return
        rel = [f"studies/{study_id}/{i}.dcm" for i in range(study.n_images)]
        try:
            res = await ml.analyze(str(study_id), rel)
        except MLServiceError as e:
            log.warning("Анализ %s не удался: %s", study_id, e)
            study.status = StudyStatus.FAILED
            study.error = str(e)
            study.finished_at = datetime.now(UTC)
            await session.commit()
            return

        study.status = StudyStatus.DONE
        study.result = res
        study.quality_ok = bool(res["quality_ok"])
        study.needs_review = bool(res["needs_review"])
        study.violation_codes = sorted({v["code"] for v in res.get("violations", [])})
        study.model_version = res.get("model_version")
        study.processing_ms = res.get("processing_ms")
        study.finished_at = datetime.now(UTC)
        study.review_status = ReviewStatus.PENDING if study.needs_review else ReviewStatus.NOT_REQUIRED
        await session.commit()


def _visible_to(user: User):
    """Лаборант видит только свои исследования, врач и админ — все."""
    if user.role == Role.TECHNOLOGIST:
        return Study.uploaded_by_id == user.id
    return True


async def list_studies(
    session: AsyncSession,
    user: User,
    *,
    status: StudyStatus | None = None,
    quality_ok: bool | None = None,
    review_status: ReviewStatus | None = None,
    code: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Study], int]:
    conds = [_visible_to(user)]
    if status is not None:
        conds.append(Study.status == status)
    if quality_ok is not None:
        conds.append(Study.quality_ok == quality_ok)
    if review_status is not None:
        conds.append(Study.review_status == review_status)
    if code:
        conds.append(Study.violation_codes.contains([code]))
    total = await session.scalar(select(func.count()).select_from(Study).where(*conds))
    rows = await session.execute(
        select(Study).where(*conds).order_by(Study.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows.scalars().all()), int(total or 0)


async def get_study(session: AsyncSession, user: User, study_id: uuid.UUID) -> Study:
    study = await session.get(Study, study_id)
    # Чужое исследование для лаборанта — 404, а не 403: не подтверждаем, что такой id существует
    if study is None or (user.role == Role.TECHNOLOGIST and study.uploaded_by_id != user.id):
        raise StudyNotFoundError(str(study_id))
    return study


async def review_study(
    session: AsyncSession, reviewer: User, study_id: uuid.UUID, quality_ok: bool, comment: str | None
) -> Study:
    study = await get_study(session, reviewer, study_id)
    if study.status != StudyStatus.DONE:
        raise InvalidUploadError("Анализ ещё не завершён")
    study.review_quality_ok = quality_ok
    study.review_comment = (comment or "").strip() or None
    study.reviewed_by_id = reviewer.id
    study.reviewed_at = datetime.now(UTC)
    study.review_status = ReviewStatus.CONFIRMED if quality_ok == study.quality_ok else ReviewStatus.CORRECTED
    await session.commit()
    await session.refresh(study)
    return study


def image_path(study_id: uuid.UUID, index: int, result: dict | None) -> Path | None:
    if not result:
        return None
    for img in result.get("images", []):
        if img["index"] == index and img.get("preview_path"):
            p = (get_settings().data_dir / img["preview_path"]).resolve()
            root = get_settings().data_dir.resolve()
            return p if p.is_relative_to(root) and p.is_file() else None
    return None
