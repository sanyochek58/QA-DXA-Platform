"""Тестовое окружение: отдельная БД dxa_test, ML-сервис подменён заглушкой.

Запуск: uv run pytest
Нужен запущенный Postgres (docker compose up -d db) и база dxa_test:
    docker compose exec db createdb -U dxa dxa_test
"""

import os
import tempfile

# Настройки должны быть выставлены ДО импорта приложения: get_settings() кешируется
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://dxa:dxa@localhost:5432/dxa_test"
)
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 40)
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="dxa-test-")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.auth import service as auth_service  # noqa: E402
from app.auth.models import Role  # noqa: E402
from app.auth.schemas import UserCreate  # noqa: E402
from app.core.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.studies.ml_client import get_ml_client  # noqa: E402

USERS = {
    "lab": ("lab@test.ru", Role.TECHNOLOGIST),
    "lab2": ("lab2@test.ru", Role.TECHNOLOGIST),
    "doctor": ("doctor@test.ru", Role.RADIOLOGIST),
    "admin": ("admin@test.ru", Role.ADMIN),
}
PASSWORD = "password123"


class FakeML:
    """Заглушка ML: первый файл «плохой», чтобы проверить нарушения и очередь врача."""

    def __init__(self) -> None:
        self.fail = False

    async def analyze(self, study_id: str, files: list[str]) -> dict:
        from app.studies.ml_client import MLServiceError

        if self.fail:
            raise MLServiceError("ML-сервис недоступен: ConnectError")
        return {
            "study_id": study_id,
            "quality_ok": False,
            "needs_review": True,
            "review_reasons": ["тест"],
            "regions": [
                {
                    "region": "spine",
                    "quality_ok": False,
                    "probability_bad": 0.8,
                    "threshold": 0.5,
                    "image_indexes": [0],
                }
            ],
            "violations": [
                {
                    "code": "SPINE_AXIS",
                    "region": "spine",
                    "severity": "critical",
                    "probability": 0.8,
                    "threshold": 0.5,
                    "title_ru": "t",
                    "message_ru": "m",
                    "how_to_fix_ru": "f",
                    "evidence": {"axis_angle_deg": 7.1},
                    "image_indexes": [0],
                }
            ],
            "images": [
                {
                    "index": i,
                    "file": f,
                    "region": "spine",
                    "region_confidence": 0.99,
                    "preview_path": None,
                    "measurements": {},
                }
                for i, f in enumerate(files)
            ],
            "metadata": {"modality": "CR"},
            "model_version": "test",
            "processing_ms": 12,
        }

    async def batch(self, archive, filename: str) -> bytes:
        return b"PK\x05\x06" + b"\0" * 18  # пустой zip

    async def health(self) -> bool:
        return True


fake_ml = FakeML()


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        for email, role in USERS.values():
            await auth_service.create_user(
                session, UserCreate(email=email, full_name=email.split("@")[0], password=PASSWORD, role=role)
            )
    app.dependency_overrides[get_ml_client] = lambda: fake_ml
    yield
    await engine.dispose()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, who: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", data={"username": USERS[who][0], "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def fake_dicom() -> bytes:
    """Минимальный «DICOM» для проверки загрузки: 128 байт преамбулы + сигнатура DICM."""
    return b"\0" * 128 + b"DICM" + b"\0" * 64
