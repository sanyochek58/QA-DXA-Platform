from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from app.auth.router import auth_router, esia_router, mock_esia_router, users_router
from app.core.config import get_settings
from app.core.db import SessionDep, engine
from app.stats.router import router as stats_router
from app.studies.ml_client import get_ml_client
from app.studies.router import router as studies_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InfoResponse(BaseModel):
    app_name: str
    debug: bool


class DatabaseHealthResponse(BaseModel):
    database: str


class SystemStatus(BaseModel):
    core: str
    database: str
    ml: str


@app.get("/health")
async def health() -> dict[str, str]:
    """Жив ли сам процесс. БД не трогаем: если упадёт база, сервер всё равно жив."""
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(session: SessionDep) -> DatabaseHealthResponse:
    """Доступна ли база. Единственный честный способ проверить — отправить ей запрос."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=503, detail="База данных недоступна") from e
    return DatabaseHealthResponse(database="ok")


# Все бизнес-эндпоинты под /api/v1 — так проще проксировать и версионировать
api = APIRouter(prefix="/api/v1")
api.include_router(auth_router)
api.include_router(esia_router)
api.include_router(mock_esia_router)
api.include_router(users_router)
api.include_router(studies_router)
api.include_router(stats_router)


@api.get("/info")
async def info() -> InfoResponse:
    return InfoResponse(app_name=settings.app_name, debug=settings.debug)


@api.get("/system/status")
async def system_status(session: SessionDep) -> SystemStatus:
    """Состояние всех частей: показываем в интерфейсе, чтобы сразу было видно, если ML лёг."""
    try:
        await session.execute(text("SELECT 1"))
        db = "ok"
    except Exception:  # noqa: BLE001
        db = "down"
    ml = "ok" if await get_ml_client().health() else "down"
    return SystemStatus(core="ok", database=db, ml=ml)


@api.get("/system/model")
async def model_info() -> dict:
    """Версия ML-модели и её метрики на кросс-валидации (для дашборда заведующего)."""
    import httpx

    try:
        async with httpx.AsyncClient(base_url=settings.ml_service_url, timeout=5) as c:
            resp = await c.get("/v1/model")
        return resp.json()
    except httpx.HTTPError:
        return {"version": None, "metrics": None}


app.include_router(api)
