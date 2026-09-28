"""HTTP-клиент к ML-сервису (аналог RestTemplate/WebClient-обёртки).

Вынесен в отдельный класс и отдаётся через зависимость, чтобы в тестах
подменить его заглушкой без поднятия настоящего ML-сервиса.
"""

from typing import Any, BinaryIO

import httpx

from app.core.config import get_settings


class MLServiceError(Exception):
    pass


class MLClient:
    def __init__(self, base_url: str, timeout: float = 300.0) -> None:
        self._base_url = base_url
        self._timeout = timeout

    async def analyze(self, study_id: str, files: list[str]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                resp = await client.post("/v1/analyze", json={"study_id": study_id, "files": files})
        except httpx.HTTPError as e:
            raise MLServiceError(f"ML-сервис недоступен: {type(e).__name__}") from e
        if resp.status_code != 200:
            detail = (
                resp.json().get("detail")
                if resp.headers.get("content-type", "").startswith("application/json")
                else resp.text
            )
            raise MLServiceError(f"ML-сервис вернул {resp.status_code}: {detail}")
        return resp.json()

    async def batch(self, archive: BinaryIO, filename: str) -> bytes:
        """Пакетная обработка zip-архива: ML возвращает zip с results.csv/xlsx и сериями."""
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=None) as client:
                files = {"archive": (filename, archive, "application/zip")}
                resp = await client.post("/v1/batch", files=files)
        except httpx.HTTPError as e:
            raise MLServiceError(f"ML-сервис недоступен: {type(e).__name__}") from e
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail")
            except ValueError:
                detail = resp.text
            raise MLServiceError(f"ML-сервис вернул {resp.status_code}: {detail}")
        return resp.content

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=3) as client:
                return (await client.get("/health")).status_code == 200
        except httpx.HTTPError:
            return False


_client: MLClient | None = None


def get_ml_client() -> MLClient:
    global _client
    if _client is None:
        _client = MLClient(get_settings().ml_service_url)
    return _client
