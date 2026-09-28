"""Аналитика качества для заведующего: доля брака, типы нарушений, разрез по лаборантам и дням."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import Date, case, cast, func, select

from app.auth.deps import AdminUser
from app.auth.models import User
from app.core.db import SessionDep
from app.studies.models import ReviewStatus, Study, StudyStatus

router = APIRouter(prefix="/stats", tags=["stats"])


class DayPoint(BaseModel):
    day: date
    total: int
    bad: int


class CodeCount(BaseModel):
    code: str
    count: int


class OperatorRow(BaseModel):
    user_id: str
    full_name: str
    total: int
    bad: int
    bad_rate: float


class Summary(BaseModel):
    days: int
    total: int
    done: int
    failed: int
    processing: int
    quality_ok: int
    quality_bad: int
    bad_rate: float
    review_pending: int
    reviewed: int
    review_agreement: float | None
    avg_processing_ms: float | None
    by_day: list[DayPoint]
    by_code: list[CodeCount]
    by_operator: list[OperatorRow]


@router.get("/summary")
async def summary(
    _: AdminUser, session: SessionDep, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> Summary:
    since = datetime.now(UTC) - timedelta(days=days)
    in_period = Study.created_at >= since

    bad = case((Study.quality_ok.is_(False), 1), else_=0)
    row = (
        await session.execute(
            select(
                func.count(),
                func.sum(case((Study.status == StudyStatus.DONE, 1), else_=0)),
                func.sum(case((Study.status == StudyStatus.FAILED, 1), else_=0)),
                func.sum(case((Study.status == StudyStatus.PROCESSING, 1), else_=0)),
                func.sum(case((Study.quality_ok.is_(True), 1), else_=0)),
                func.sum(bad),
                func.sum(case((Study.review_status == ReviewStatus.PENDING, 1), else_=0)),
                func.sum(case((Study.review_status == ReviewStatus.CONFIRMED, 1), else_=0)),
                func.sum(case((Study.review_status == ReviewStatus.CORRECTED, 1), else_=0)),
                func.avg(Study.processing_ms),
            ).where(in_period)
        )
    ).one()
    total, done, failed, processing, ok, nbad, pending, confirmed, corrected, avg_ms = (
        int(x or 0) if i < 9 else x for i, x in enumerate(row)
    )
    reviewed = confirmed + corrected

    day_col = cast(Study.created_at, Date)
    by_day = [
        DayPoint(day=d, total=t, bad=int(b or 0))
        for d, t, b in (
            await session.execute(
                select(day_col, func.count(), func.sum(bad))
                .where(in_period)
                .group_by(day_col)
                .order_by(day_col)
            )
        ).all()
    ]

    code = func.unnest(Study.violation_codes).label("code")
    sub = select(code).where(in_period).subquery()
    by_code = [
        CodeCount(code=c, count=n)
        for c, n in (
            await session.execute(
                select(sub.c.code, func.count()).group_by(sub.c.code).order_by(func.count().desc())
            )
        ).all()
    ]

    by_operator = []
    for uid, name, t, b in (
        await session.execute(
            select(User.id, User.full_name, func.count(Study.id), func.sum(bad))
            .join(Study, Study.uploaded_by_id == User.id)
            .where(in_period, Study.status == StudyStatus.DONE)
            .group_by(User.id, User.full_name)
            .order_by(func.count(Study.id).desc())
        )
    ).all():
        b = int(b or 0)
        by_operator.append(
            OperatorRow(
                user_id=str(uid), full_name=name, total=t, bad=b, bad_rate=round(b / t, 3) if t else 0.0
            )
        )

    return Summary(
        days=days,
        total=total,
        done=done,
        failed=failed,
        processing=processing,
        quality_ok=ok,
        quality_bad=nbad,
        bad_rate=round(nbad / done, 3) if done else 0.0,
        review_pending=pending,
        reviewed=reviewed,
        review_agreement=round(confirmed / reviewed, 3) if reviewed else None,
        avg_processing_ms=round(float(avg_ms), 1) if avg_ms is not None else None,
        by_day=by_day,
        by_code=by_code,
        by_operator=by_operator,
    )
