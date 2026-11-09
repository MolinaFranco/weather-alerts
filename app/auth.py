from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from app.config import settings
from app.db import SessionDep
from app.enums import Role
from app.models import User

passwords = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# Roles are cumulative: each one can do everything the previous one can.
ROLE_ORDER = [Role.CLIENT, Role.TECHNICIAN, Role.ADMIN]

# Verified when the login doesn't match any user, so a wrong email takes as long as a
# wrong password and response times don't reveal which accounts exist.
UNKNOWN_USER_HASH = passwords.hash("not a real password")


# argon2 is slow on purpose (tens of milliseconds), so it runs off the event loop.
async def hash_password(password: str) -> str:
    return await run_in_threadpool(passwords.hash, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await run_in_threadpool(passwords.verify, password, password_hash)


def create_access_token(user_id: int) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expires}, settings.jwt_secret, "HS256")


async def current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
        user = await session.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, ValueError):
        raise unauthorized from None
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def is_staff(user: User) -> bool:
    return user.role != Role.CLIENT


def require_role(minimum: Role):
    async def check(user: CurrentUser) -> User:
        if ROLE_ORDER.index(user.role) < ROLE_ORDER.index(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role can't do this")
        return user

    return Depends(check)


Technician = Annotated[User, require_role(Role.TECHNICIAN)]
Admin = Annotated[User, require_role(Role.ADMIN)]
