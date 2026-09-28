"""Демо-исследования для тестирования и защиты.

Берёт DICOM из папки (каждая подпапка = одно исследование, как в датасете организаторов),
раскидывает загрузки по последним 30 дням и двум лаборантам, прогоняет через настоящий
ML-сервис и оставляет часть решений врача, чтобы сводка и очередь не были пустыми.

Нужны: запущенный ML-сервис и выполненный seed (сотрудники).

Запуск:
    uv run python -m app.scripts.seed_demo                       # 24 исследования из data/train
    uv run python -m app.scripts.seed_demo --src ../../data/demo --limit 10
    uv run python -m app.scripts.seed_demo --if-empty            # только если исследований ещё нет
"""

import argparse
import asyncio
import os
import random
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.auth import service as auth_service
from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.studies import service
from app.studies.ml_client import MLClient
from app.studies.models import ReviewStatus, Study, StudyStatus

DEFAULT_SRC = os.getenv("DEMO_SRC", "../../data/train/Исследования")
LABS = ["lab@dxa-qa.ru", "lab2@dxa-qa.ru"]
DOCTOR = "doctor@dxa-qa.ru"
COMMENTS_OK = [
    "Укладка допустима, разметка L1–L4 корректна",
    "Сколиоз, ось отклонена по анатомии — пересъёмка не нужна",
]
COMMENTS_BAD = ["Бедро ротировано, малый вертел виден полностью — переснять", "Металл в поле сканирования"]


def is_dicom(p: Path) -> bool:
    try:
        with p.open("rb") as f:
            return f.read(132)[128:132] == b"DICM"
    except OSError:
        return False


def find_studies(src: Path) -> list[list[Path]]:
    """Подпапка первого уровня = исследование; внутри DICOM ищем рекурсивно."""
    out = []
    for d in sorted(p for p in src.iterdir() if p.is_dir()):
        files = sorted(f for f in d.rglob("*") if f.is_file() and is_dicom(f))
        if files:
            out.append(files[:40])
    loose = sorted(f for f in src.iterdir() if f.is_file() and is_dicom(f))
    if loose:
        out.append(loose[:40])
    return out


async def wait_ml(ml: MLClient, seconds: int = 120) -> bool:
    for _ in range(seconds // 3):
        if await ml.health():
            return True
        await asyncio.sleep(3)
    return False


async def main(src: Path, limit: int, if_empty: bool) -> None:
    if not src.is_dir():
        print(f"Папка с DICOM не найдена: {src}. Укажите --src или DEMO_SRC. Пропускаю.")
        return
    settings = get_settings()
    ml = MLClient(settings.ml_service_url)
    rnd = random.Random(42)  # одинаковые данные при каждом запуске

    async with SessionLocal() as session:
        if if_empty and (await session.scalar(select(func.count()).select_from(Study))):
            print("Исследования уже есть, --if-empty: пропускаю")
            return
        labs = [await auth_service.get_by_email(session, e) for e in LABS]
        doctor = await auth_service.get_by_email(session, DOCTOR)
        if not all(labs) or doctor is None:
            print("Сначала выполните: python -m app.scripts.seed")
            return

    if not await wait_ml(ml):
        print(f"ML-сервис {settings.ml_service_url} не отвечает. Пропускаю.")
        return

    groups = find_studies(src)
    rnd.shuffle(groups)
    groups = groups[:limit]
    now = datetime.now(UTC)
    print(f"Загружаю {len(groups)} исследований из {src}")

    for n, files in enumerate(groups, 1):
        async with SessionLocal() as session:
            lab = labs[0] if rnd.random() < 0.6 else labs[1]
            ago = timedelta(days=rnd.randint(0, 29), hours=rnd.randint(0, 9), minutes=rnd.randint(0, 59))
            created = now - ago
            study = Study(
                uploaded_by_id=lab.id,
                title=f"Кабинет {rnd.randint(1, 3)}, пациент {n:02d}",
                file_names=[f"image_{i + 1}.dcm" for i in range(len(files))],
                n_images=len(files),
                created_at=created,
            )
            session.add(study)
            await session.flush()
            target = service.study_dir(study.id)
            target.mkdir(parents=True, exist_ok=True)
            for i, f in enumerate(files):
                shutil.copyfile(f, target / f"{i}.dcm")
            await session.commit()
            study_id = study.id

        await service.process_study(study_id, ml)

        async with SessionLocal() as session:
            study = await session.get(Study, study_id)
            if study.status != StudyStatus.DONE:
                print(f"  {n:02d}: ошибка анализа — {study.error}")
                continue
            study.finished_at = study.created_at + timedelta(seconds=rnd.randint(3, 9))
            # Врач разобрал примерно половину сомнительных случаев
            if study.review_status == ReviewStatus.PENDING and rnd.random() < 0.5:
                agree = rnd.random() < 0.8
                ok = study.quality_ok if agree else not study.quality_ok
                study.review_quality_ok = ok
                study.review_comment = rnd.choice(COMMENTS_OK if ok else COMMENTS_BAD)
                study.reviewed_by_id = doctor.id
                study.reviewed_at = study.finished_at + timedelta(hours=rnd.randint(1, 20))
                study.review_status = ReviewStatus.CONFIRMED if agree else ReviewStatus.CORRECTED
            await session.commit()
            verdict = "норма" if study.quality_ok else ", ".join(study.violation_codes) or "нарушение"
            print(f"  {n:02d}: {len(files)} сним. — {verdict}")
    await engine.dispose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=Path(DEFAULT_SRC))
    ap.add_argument("--limit", type=int, default=24)
    ap.add_argument("--if-empty", action="store_true")
    args = ap.parse_args()
    asyncio.run(main(args.src, args.limit, args.if_empty))
