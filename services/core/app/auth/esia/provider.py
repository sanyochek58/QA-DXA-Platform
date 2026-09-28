"""Провайдеры ЕСИА.

Поток один и тот же для mock и real (OAuth 2.0 authorization code):
  1. фронт просит у core /auth/esia/start → получает URL авторизации и подписанный state;
  2. браузер уходит на ЕСИА (или mock-страницу), пользователь входит;
  3. ЕСИА редиректит на {frontend}/auth/esia/callback?code=...&state=...;
  4. фронт отдаёт code+state в core /auth/esia/callback;
  5. core меняет code на данные человека (oid, СНИЛС, ФИО) и ищет сотрудника.

Mock нужен для разработки и защиты: реальная ЕСИА требует регистрации ИС
и подписи запросов сертификатом ГОСТ (КриптоПро), которых у хакатона нет.
"""

import base64
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from urllib.parse import urlencode

import httpx
import jwt

from app.auth.esia import snils as snils_lib
from app.core.config import get_settings

CODE_AUDIENCE = "esia-mock-code"
STATE_AUDIENCE = "esia-state"


class EsiaError(Exception):
    """Ошибка обмена с ЕСИА: неверный code, истёк срок, сеть и т.п."""


@dataclass(frozen=True)
class EsiaPerson:
    oid: str
    snils: str  # 11 цифр
    last_name: str
    first_name: str
    middle_name: str
    email: str | None = None
    phone: str | None = None

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p)


class EsiaProvider(Protocol):
    mode: str

    def authorize_url(self, state: str, redirect_uri: str) -> str: ...

    async def exchange(self, code: str, redirect_uri: str, state: str) -> EsiaPerson: ...


# ---------- state: подписанный JWT, чтобы не хранить его на сервере ----------


def issue_state() -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "aud": STATE_AUDIENCE,
        "nonce": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(minutes=10),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def verify_state(state: str) -> None:
    s = get_settings()
    try:
        jwt.decode(state, s.jwt_secret, algorithms=[s.jwt_algorithm], audience=STATE_AUDIENCE)
    except jwt.InvalidTokenError as e:
        raise EsiaError("Сессия входа истекла или state подделан. Начните вход заново.") from e


# ---------- mock ----------


def _p(oid: str, first9: str, last: str, first: str, middle: str, email: str, phone: str) -> EsiaPerson:
    return EsiaPerson(oid, snils_lib.make(first9), last, first, middle, email, phone)


# Тестовые учётные записи «Госуслуг». Пароль у всех один: MOCK_PASSWORD.
MOCK_PERSONS: list[EsiaPerson] = [
    _p("1000000001", "112233445", "Садыкова", "Ирина", "Рашидовна", "sadykova@example.ru", "+79000000001"),
    _p(
        "1000000002",
        "156782394",
        "Веретенников",
        "Олег",
        "Игоревич",
        "veretennikov@example.ru",
        "+79000000002",
    ),
    _p("1000000003", "200300400", "Лебедева", "Мария", "Сергеевна", "lebedeva@example.ru", "+79000000003"),
    _p("1000000004", "301402503", "Корнилов", "Андрей", "Викторович", "kornilov@example.ru", "+79000000004"),
    _p("1000000005", "412503604", "Григорьева", "Елена", "Павловна", "grigorieva@example.ru", "+79000000005"),
    _p("1000000006", "523604705", "Смирнов", "Павел", "Андреевич", "smirnov@example.ru", "+79000000006"),
]
MOCK_PASSWORD = "esia12345"


def find_mock_person(login: str) -> EsiaPerson | None:
    """ЕСИА пускает по СНИЛС, телефону или email — повторяем это."""
    login = login.strip().lower()
    digits = "".join(ch for ch in login if ch.isdigit())
    for p in MOCK_PERSONS:
        if login == (p.email or "").lower():
            return p
        if digits and digits == p.snils:
            return p
        if digits and p.phone and digits[-10:] == p.phone[-10:] and len(digits) >= 10:
            return p
    return None


def issue_mock_code(person: EsiaPerson, redirect_uri: str) -> str:
    """Код авторизации — короткоживущий подписанный JWT с oid и redirect_uri."""
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "aud": CODE_AUDIENCE,
        "sub": person.oid,
        "ruri": redirect_uri,
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(seconds=120),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


class MockEsiaProvider:
    mode = "mock"

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        query = urlencode({"state": state, "redirect_uri": redirect_uri, "scope": get_settings().esia_scope})
        # Mock-страница входа живёт во фронтенде, на том же origin, что и callback
        origin = redirect_uri.split("/auth/esia/callback")[0]
        return f"{origin}/esia-test/login?{query}"

    async def exchange(self, code: str, redirect_uri: str, state: str) -> EsiaPerson:
        s = get_settings()
        try:
            data = jwt.decode(code, s.jwt_secret, algorithms=[s.jwt_algorithm], audience=CODE_AUDIENCE)
        except jwt.InvalidTokenError as e:
            raise EsiaError("Код авторизации недействителен или истёк") from e
        if data.get("ruri") != redirect_uri:
            raise EsiaError("redirect_uri не совпадает с тем, что был при авторизации")
        person = next((p for p in MOCK_PERSONS if p.oid == data["sub"]), None)
        if person is None:
            raise EsiaError("Учётная запись ЕСИА не найдена")
        return person


# ---------- реальная ЕСИА ----------


class RealEsiaProvider:
    """Клиент боевой/тестовой ЕСИА по методическим рекомендациям (OAuth 2.0, v2/ac + v3/te).

    Что нужно для запуска:
      * ИС зарегистрирована в ЕСИА, выдан client_id (мнемоника), в кабинете указан redirect_uri;
      * сертификат ГОСТ Р 34.10-2012, его хеш — ESIA_CERT_HASH;
      * сервис подписи ESIA_SIGNER_URL: принимает байты, возвращает открепленную подпись
        (обычно отдельный контейнер с КриптоПро CSP — в Python ГОСТ-подпись сама не делается).
    Перед запуском сверьте параметры с актуальной версией методических рекомендаций.
    """

    mode = "real"

    def __init__(self) -> None:
        self.s = get_settings()
        if not (self.s.esia_client_id and self.s.esia_signer_url and self.s.esia_cert_hash):
            raise RuntimeError("Для ESIA_MODE=real нужны ESIA_CLIENT_ID, ESIA_SIGNER_URL и ESIA_CERT_HASH")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).strftime("%Y.%m.%d %H:%M:%S +0000")

    def _sign(self, message: str) -> str:
        resp = httpx.post(str(self.s.esia_signer_url), content=message.encode(), timeout=10)
        resp.raise_for_status()
        return base64.urlsafe_b64encode(resp.content).decode().rstrip("=")

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        # ЕСИА ждёт state в формате UUID; наш подписанный state кладём в redirect_uri
        esia_state = str(uuid.uuid4())
        ts = self._timestamp()
        scope = self.s.esia_scope
        cid = self.s.esia_client_id
        ruri = f"{redirect_uri}?{urlencode({'app_state': state})}"
        secret = self._sign(cid + scope + ts + esia_state + ruri)
        params = {
            "client_id": cid,
            "client_secret": secret,
            "client_certificate_hash": self.s.esia_cert_hash,
            "redirect_uri": ruri,
            "scope": scope,
            "response_type": "code",
            "state": esia_state,
            "timestamp": ts,
            "access_type": "online",
        }
        return f"{self.s.esia_base_url}/aas/oauth2/v2/ac?{urlencode(params)}"

    async def exchange(self, code: str, redirect_uri: str, state: str) -> EsiaPerson:
        redirect_uri = f"{redirect_uri}?{urlencode({'app_state': state})}"  # тот же, что в authorize_url
        ts = self._timestamp()
        esia_state = str(uuid.uuid4())
        cid, scope = self.s.esia_client_id, self.s.esia_scope
        secret = self._sign(cid + scope + ts + esia_state + redirect_uri + code)
        form = {
            "client_id": cid,
            "code": code,
            "grant_type": "authorization_code",
            "client_secret": secret,
            "client_certificate_hash": self.s.esia_cert_hash,
            "state": esia_state,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "timestamp": ts,
            "token_type": "Bearer",
        }
        base = self.s.esia_base_url
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                tok = (await c.post(f"{base}/aas/oauth2/v3/te", data=form)).raise_for_status().json()
                access = tok["access_token"]
                # Подпись маркера проверяет ЕСИА при обращении к REST; oid берём из payload
                oid = str(jwt.decode(access, options={"verify_signature": False})["urn:esia:sbj_id"])
                h = {"Authorization": f"Bearer {access}"}
                prn = (await c.get(f"{base}/rs/prns/{oid}", headers=h)).raise_for_status().json()
        except (httpx.HTTPError, KeyError, jwt.InvalidTokenError) as e:
            raise EsiaError(f"ЕСИА отклонила обмен кода: {type(e).__name__}") from e
        return EsiaPerson(
            oid=oid,
            snils=snils_lib.normalize(prn.get("snils", "")),
            last_name=prn.get("lastName", ""),
            first_name=prn.get("firstName", ""),
            middle_name=prn.get("middleName", ""),
        )


def get_provider() -> EsiaProvider | None:
    mode = get_settings().esia_mode
    if mode == "mock":
        return MockEsiaProvider()
    if mode == "real":
        return RealEsiaProvider()
    return None
