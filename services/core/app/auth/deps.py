"""Зависимости безопасности. Аналог SecurityFilterChain + @PreAuthorize.

Эндпоинт, который принимает `user: CurrentUser`, без валидного токена просто не выполнится.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.auth.models import Role, User
from app.core.db import SessionDep
from app.core.security import decode_access_token

# tokenUrl нужен Swagger UI: появится кнопка Authorize с формой логина
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Сессия истекла или токен недействителен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise credentials_error from None

    # Роль берём из БД, а не из токена: блокировка и смена роли работают сразу
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], Awaitable[User]]:
    """require_roles(Role.ADMIN) ~ @PreAuthorize("hasRole('ADMIN')")."""

    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user

    return checker


AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
ReviewerUser = Annotated[User, Depends(require_roles(Role.RADIOLOGIST, Role.ADMIN))]
