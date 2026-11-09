from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select

from app.auth import UNKNOWN_USER_HASH, CurrentUser, create_access_token, passwords
from app.db import SessionDep
from app.models import Membership, Organization, User
from app.schemas import Me, OrganizationOut, Token, UserCreate, UserOut

router = APIRouter(tags=["auth"])


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, session: SessionDep) -> UserOut:
    """Sign up as a client. Organizations are set up by staff."""
    user = User(
        name=body.name,
        email=body.email.lower(),
        phone=body.phone,
        password_hash=passwords.hash(body.password),
    )
    session.add(user)
    await session.commit()
    return UserOut.model_validate(user)


@router.post("/auth/token")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    """Log in with email (web) or phone (WhatsApp) as the username."""
    username = form.username.strip()
    user = await session.scalar(
        select(User).where(or_(func.lower(User.email) == username.lower(), User.phone == username))
    )
    if user is None:
        passwords.verify(form.password, UNKNOWN_USER_HASH)
    if user is None or not passwords.verify(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong username or password")
    return Token(access_token=create_access_token(user.id))


@router.get("/me")
async def me(user: CurrentUser, session: SessionDep) -> Me:
    """The current user and the organizations they are a member of."""
    organizations = await session.scalars(
        select(Organization)
        .join(Membership)
        .where(Membership.user_id == user.id)
        .order_by(Organization.name)
    )
    return Me(
        **UserOut.model_validate(user).model_dump(),
        organizations=[OrganizationOut.model_validate(o) for o in organizations],
    )
