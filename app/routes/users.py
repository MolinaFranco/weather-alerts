from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.access import get_or_404
from app.auth import Admin, Technician, hash_password
from app.db import SessionDep
from app.models import Membership, User
from app.schemas import PathId, StaffUserCreate, UserOut, UserRoleUpdate

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
        email=body.email,
        phone=body.phone,
        password_hash=await hash_password(body.password),
    )
    session.add(user)
    await session.flush()
    session.add_all(
        Membership(user_id=user.id, organization_id=organization_id)
        for organization_id in set(body.organization_ids)
    )
    await session.commit()
    return UserOut.model_validate(user)


def refuse_own_account(admin: Admin, user_id: int) -> None:
    # Otherwise the last admin could demote or delete themselves and lock everyone out.
    if admin.id == user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Admins can't change their own account")


@router.patch("/{user_id}")
async def change_role(
    user_id: PathId, body: UserRoleUpdate, admin: Admin, session: SessionDep
) -> UserOut:
    refuse_own_account(admin, user_id)
    user = await get_or_404(session, User, user_id)
    user.role = body.role
    await session.commit()
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: PathId, admin: Admin, session: SessionDep) -> None:
    refuse_own_account(admin, user_id)
    await session.delete(await get_or_404(session, User, user_id))
    await session.commit()
