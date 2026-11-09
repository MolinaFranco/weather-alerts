from fastapi import APIRouter, status
from sqlalchemy import select

from app.access import not_found
from app.auth import Admin, Technician, passwords
from app.db import SessionDep
from app.models import Membership, User
from app.schemas import StaffUserCreate, UserOut, UserRoleUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(_: Technician, session: SessionDep) -> list[UserOut]:
    users = await session.scalars(select(User).order_by(User.name))
    return [UserOut.model_validate(user) for user in users]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(body: StaffUserCreate, _: Technician, session: SessionDep) -> UserOut:
    """Create a client, optionally already inside some organizations."""
    user = User(
        name=body.name,
        email=body.email.lower(),
        phone=body.phone,
        password_hash=passwords.hash(body.password),
    )
    session.add(user)
    await session.flush()
    session.add_all(
        Membership(user_id=user.id, organization_id=organization_id)
        for organization_id in set(body.organization_ids)
    )
    await session.commit()
    return UserOut.model_validate(user)


@router.patch("/{user_id}")
async def change_role(user_id: int, body: UserRoleUpdate, _: Admin, session: SessionDep) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise not_found()
    user.role = body.role
    await session.commit()
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, _: Admin, session: SessionDep) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise not_found()
    await session.delete(user)
    await session.commit()
