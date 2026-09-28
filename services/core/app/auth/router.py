import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import service
from app.auth.deps import AdminUser, CurrentUser
from app.auth.esia import provider as esia
from app.auth.esia.snils import format_snils
from app.auth.schemas import (
    EsiaCallback,
    EsiaConfig,
    EsiaStart,
    MockEsiaLogin,
    MockEsiaPerson,
    MockEsiaRedirect,
    Token,
    UserCreate,
    UserRead,
    UserUpdate,
)
from app.core.config import get_settings
from app.core.db import SessionDep
from app.core.security import create_access_token

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@auth_router.post("/login")
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep) -> Token:
    # Стандарт OAuth2: форма с полями username и password. В username кладём email.
    user = await service.authenticate(session, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(str(user.id), user.role.value))


@auth_router.get("/me")
async def me(user: CurrentUser) -> UserRead:
    return UserRead.from_user(user)


@users_router.get("")
async def list_users(_: AdminUser, session: SessionDep) -> list[UserRead]:
    return [UserRead.from_user(u) for u in await service.list_users(session)]


@users_router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, _: AdminUser, session: SessionDep) -> UserRead:
    try:
        user = await service.create_user(session, data)
    except service.EmailAlreadyExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким email уже существует") from None
    except service.SnilsAlreadyExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сотрудник с таким СНИЛС уже есть") from None
    return UserRead.from_user(user)


@users_router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID, data: UserUpdate, admin: AdminUser, session: SessionDep
) -> UserRead:
    if user_id == admin.id and (data.is_active is False or (data.role and data.role != admin.role)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя заблокировать себя или снять с себя роль")
    try:
        user = await service.update_user(session, user_id, data)
    except service.UserNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пользователь не найден") from None
    except service.SnilsAlreadyExistsError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Сотрудник с таким СНИЛС уже есть") from None
    return UserRead.from_user(user)


# ---------------- Вход через Госуслуги (ЕСИА) ----------------

esia_router = APIRouter(prefix="/auth/esia", tags=["esia"])
mock_esia_router = APIRouter(prefix="/esia-test", tags=["esia-mock"])


def _check_redirect(redirect_uri: str) -> str:
    """Разрешаем возврат только на свой фронтенд — иначе code можно увести на чужой сайт."""
    allowed = {f"{o.rstrip('/')}/auth/esia/callback" for o in get_settings().cors_origins}
    if redirect_uri not in allowed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Недопустимый адрес возврата")
    return redirect_uri


def _provider() -> esia.EsiaProvider:
    provider = esia.get_provider()
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вход через Госуслуги отключён")
    return provider


@esia_router.get("/config")
async def esia_config() -> EsiaConfig:
    mode = get_settings().esia_mode
    return EsiaConfig(enabled=mode != "off", mode=mode)


@esia_router.get("/start")
async def esia_start(redirect_uri: str) -> EsiaStart:
    provider = _provider()
    state = esia.issue_state()
    return EsiaStart(url=provider.authorize_url(state, _check_redirect(redirect_uri)), state=state)


@esia_router.post("/callback")
async def esia_callback(data: EsiaCallback, session: SessionDep) -> Token:
    provider = _provider()
    redirect_uri = _check_redirect(data.redirect_uri)
    try:
        esia.verify_state(data.state)
        person = await provider.exchange(data.code, redirect_uri, data.state)
    except esia.EsiaError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from None
    try:
        user = await service.login_via_esia(session, person.oid, person.snils)
    except service.EsiaUserNotRegisteredError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"{person.full_name}, вашего СНИЛС нет среди сотрудников отделения. "
            "Попросите заведующего добавить вас и указать СНИЛС.",
        ) from None
    except service.UserBlockedError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Учётная запись заблокирована. Обратитесь к заведующему."
        ) from None
    return Token(access_token=create_access_token(str(user.id), user.role.value))


# Mock-ЕСИА: только в ESIA_MODE=mock. Имитирует страницу входа и выдачу кода авторизации.


def _require_mock() -> None:
    if get_settings().esia_mode != "mock":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Тестовый контур ЕСИА отключён")


@mock_esia_router.get("/persons")
async def mock_persons() -> list[MockEsiaPerson]:
    _require_mock()
    return [
        MockEsiaPerson(full_name=p.full_name, snils=format_snils(p.snils), email=p.email, phone=p.phone)
        for p in esia.MOCK_PERSONS
    ]


@mock_esia_router.post("/authorize")
async def mock_authorize(data: MockEsiaLogin) -> MockEsiaRedirect:
    _require_mock()
    redirect_uri = _check_redirect(data.redirect_uri)
    person = esia.find_mock_person(data.login)
    if person is None or data.password != esia.MOCK_PASSWORD:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    code = esia.issue_mock_code(person, redirect_uri)
    return MockEsiaRedirect(redirect=f"{redirect_uri}?{urlencode({'code': code, 'state': data.state})}")
