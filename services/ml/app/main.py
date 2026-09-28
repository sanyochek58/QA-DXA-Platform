"""ML-сервис. Без БД и пользователей: получил пути к DICOM — вернул вердикт.

Запуск локально: uv run fastapi dev app/main.py --port 8001
"""

import json
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.batch import run_batch
from app.pipeline.analyzer import ROOT, Analyzer
from app.schemas import AnalyzeRequest, AnalyzeResponse

DATA_DIR = Path(os.getenv("DATA_DIR", "../../data/runtime")).resolve()

state: dict[str, Analyzer] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Модель грузим один раз при старте (как @PostConstruct), а не на каждый запрос
    state["analyzer"] = Analyzer()
    yield
    state.clear()


app = FastAPI(title="DXA-QA ML", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": state["analyzer"].version if state else "not loaded"}


@app.get("/v1/model")
async def model_info() -> dict:
    """Версия модели и метрики кросс-валидации — показываем на дашборде."""
    metrics = ROOT / "models" / "metrics.json"
    return {
        "version": state["analyzer"].version,
        "metrics": json.loads(metrics.read_text("utf-8")) if metrics.exists() else None,
    }


@app.post("/v1/analyze")
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    paths = []
    for rel in req.files:
        p = (DATA_DIR / rel).resolve()
        # Защита от path traversal: "../../etc/passwd" не выйдет за пределы DATA_DIR
        if not p.is_relative_to(DATA_DIR):
            raise HTTPException(400, "Путь вне каталога данных")
        if not p.is_file():
            raise HTTPException(404, f"Файл не найден: {rel}")
        paths.append(p)
    # Анализ — тяжёлая синхронная работа (CPU). В async-функции она заблокировала бы
    # event loop и сервис перестал бы отвечать всем. Поэтому уводим в пул потоков.
    try:
        return await run_in_threadpool(state["analyzer"].analyze, req.study_id, paths, req.files, DATA_DIR)
    except Exception as e:
        raise HTTPException(422, f"Не удалось обработать исследование: {type(e).__name__}: {e}") from e


@app.post(
    "/v1/batch",
    response_class=FileResponse,
    responses={200: {"content": {"application/zip": {}}, "description": "results.csv, results.xlsx, series/"}},
)
async def batch(
    background: BackgroundTasks,
    archive: Annotated[UploadFile, File(description="zip с DICOM-исследованиями")],
):
    """Пакетная обработка: zip с исследованиями -> zip с отчётом (csv, xlsx) и дополнительными сериями.

    Пример: curl -F archive=@studies.zip http://localhost:8001/v1/batch -o results.zip
    """
    tmp = Path(tempfile.mkdtemp(prefix="dxa-api-batch-"))
    background.add_task(shutil.rmtree, tmp, True)  # удалить временные файлы после отправки ответа
    src = tmp / "input.zip"
    with src.open("wb") as f:
        while chunk := await archive.read(1024 * 1024):
            f.write(chunk)
    out = tmp / "out"
    try:
        await run_in_threadpool(run_batch, src, out, state["analyzer"], lambda *_: None)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    (out / "series.zip").unlink(missing_ok=True)  # серии и так лежат в папке series/ внутри ответа
    result = Path(shutil.make_archive(str(tmp / "results"), "zip", out))
    return FileResponse(result, media_type="application/zip", filename="dxa_qa_results.zip")
