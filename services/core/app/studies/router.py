import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.auth.deps import CurrentUser, ReviewerUser
from app.core.db import SessionDep
from app.studies import service
from app.studies.ml_client import MLClient, MLServiceError, get_ml_client
from app.studies.models import ReviewStatus, StudyStatus
from app.studies.schemas import ReviewCreate, StudyListItem, StudyPage, StudyRead

router = APIRouter(prefix="/studies", tags=["studies"])

MLDep = Annotated[MLClient, Depends(get_ml_client)]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_study(
    user: CurrentUser,
    session: SessionDep,
    ml: MLDep,
    background: BackgroundTasks,
    files: Annotated[list[UploadFile], File(description="DICOM-файлы одного исследования")],
    title: Annotated[str | None, Form(max_length=255)] = None,
) -> StudyRead:
    """Загрузить исследование. Ответ приходит сразу (202), анализ идёт в фоне:
    статус смотрим через GET /studies/{id}."""
    try:
        study = await service.create_study(session, user, files, title)
    except service.InvalidUploadError as e:
        raise HTTPException(422, str(e)) from None
    background.add_task(service.process_study, study.id, ml)
    return StudyRead.model_validate(study)


@router.post(
    "/batch",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}, "description": "results.csv/xlsx и series/"}},
)
async def batch(
    _: ReviewerUser,
    ml: MLDep,
    archive: Annotated[UploadFile, File(description="zip с DICOM-исследованиями")],
) -> Response:
    """Пакетная проверка архива исследований (врач, заведующий). Результаты в БД не сохраняются:
    это режим для выгрузки отчёта, а не для рабочего потока отделения."""
    if not (archive.filename or "").lower().endswith(".zip"):
        raise HTTPException(422, "Нужен zip-архив с DICOM-исследованиями")
    try:
        content = await ml.batch(archive.file, archive.filename or "studies.zip")
    except MLServiceError as e:
        raise HTTPException(502, str(e)) from None
    return Response(
        content,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="dxa_qa_results.zip"'},
    )


@router.get("")
async def list_studies(
    user: CurrentUser,
    session: SessionDep,
    status_: Annotated[StudyStatus | None, Query(alias="status")] = None,
    quality_ok: bool | None = None,
    review_status: ReviewStatus | None = None,
    code: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StudyPage:
    items, total = await service.list_studies(
        session,
        user,
        status=status_,
        quality_ok=quality_ok,
        review_status=review_status,
        code=code,
        limit=limit,
        offset=offset,
    )
    return StudyPage(items=[StudyListItem.model_validate(s) for s in items], total=total)


@router.get("/queue")
async def review_queue(user: ReviewerUser, session: SessionDep) -> StudyPage:
    """Очередь врача: исследования, в которых модель не уверена."""
    items, total = await service.list_studies(session, user, review_status=ReviewStatus.PENDING, limit=200)
    return StudyPage(items=[StudyListItem.model_validate(s) for s in items], total=total)


@router.get("/{study_id}")
async def get_study(study_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> StudyRead:
    try:
        return StudyRead.model_validate(await service.get_study(session, user, study_id))
    except service.StudyNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Исследование не найдено") from None


@router.get("/{study_id}/images/{index}", response_class=FileResponse)
async def get_image(study_id: uuid.UUID, index: int, user: CurrentUser, session: SessionDep) -> FileResponse:
    try:
        study = await service.get_study(session, user, study_id)
    except service.StudyNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Исследование не найдено") from None
    path = service.image_path(study.id, index, study.result)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Изображение не найдено")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/{study_id}/review")
async def review(
    study_id: uuid.UUID, data: ReviewCreate, user: ReviewerUser, session: SessionDep
) -> StudyRead:
    try:
        study = await service.review_study(session, user, study_id, data.quality_ok, data.comment)
    except service.StudyNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Исследование не найдено") from None
    except service.InvalidUploadError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    return StudyRead.model_validate(study)


@router.post("/{study_id}/reanalyze", status_code=status.HTTP_202_ACCEPTED)
async def reanalyze(
    study_id: uuid.UUID, user: CurrentUser, session: SessionDep, ml: MLDep, background: BackgroundTasks
) -> StudyRead:
    """Повторный анализ (например, после обновления модели или если ML был недоступен)."""
    try:
        study = await service.get_study(session, user, study_id)
    except service.StudyNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Исследование не найдено") from None
    study.status = StudyStatus.PROCESSING
    study.error = None
    await session.commit()
    await session.refresh(study)
    background.add_task(service.process_study, study.id, ml)
    return StudyRead.model_validate(study)
