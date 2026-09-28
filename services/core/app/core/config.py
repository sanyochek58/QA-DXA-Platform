from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    app_name: str = "DXA-QA Platform"
    debug: bool = False
    database_url: str
    jwt_secret: str = Field(min_length=32, max_length=128)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 480

    # Адрес ML-сервиса. Локально — localhost, в docker-compose — имя сервиса (http://ml:8001)
    ml_service_url: str = "http://localhost:8001"
    # Общая папка с DICOM и превью. Её же видит ML-сервис (общий том в Docker)
    data_dir: Path = Path("../../data/runtime")
    # Лимит на один загружаемый файл, МБ
    max_upload_mb: int = 50
    cors_origins: list[str] = ["http://localhost:5173"]

    # Вход через ЕСИА (Госуслуги): off — выключен, mock — тестовый контур внутри приложения,
    # real — настоящая ЕСИА (нужны регистрация ИС, сертификат ГОСТ и сервис подписи)
    esia_mode: Literal["off", "mock", "real"] = "mock"
    esia_base_url: str = "https://esia-portal1.test.gosuslugi.ru"
    esia_client_id: str = ""
    esia_scope: str = "openid fullname snils"
    esia_cert_hash: str = ""
    esia_signer_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
