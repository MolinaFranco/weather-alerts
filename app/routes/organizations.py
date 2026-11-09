from fastapi import APIRouter, status
from sqlalchemy import delete, select

from app.access import get_visible_organization, not_found, visible_organizations
from app.auth import Admin, CurrentUser, Technician
from app.db import SessionDep
from app.models import Membership, Organization, User
from app.schemas import (
    MemberAdd,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    UserOut,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("")
async def list_organizations(user: CurrentUser, session: SessionDep) -> list[OrganizationOut]:
    """Clients see the organizations they belong to; staff see all of them."""
    organizations = await session.scalars(visible_organizations(user).order_by(Organization.name))
    return [OrganizationOut.model_validate(o) for o in organizations]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate, _: Technician, session: SessionDep
) -> OrganizationOut:
    organization = Organization(name=body.name)
    session.add(organization)
    await session.flush()
    session.add_all(
        Membership(user_id=user_id, organization_id=organization.id)
        for user_id in set(body.member_ids)
    )
    await session.commit()
    return OrganizationOut.model_validate(organization)


@router.patch("/{organization_id}")
async def rename_organization(
    organization_id: int, body: OrganizationUpdate, _: Technician, session: SessionDep
) -> OrganizationOut:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise not_found()
    organization.name = body.name
    await session.commit()
    return OrganizationOut.model_validate(organization)


@router.delete("/{organization_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(organization_id: int, _: Admin, session: SessionDep) -> None:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise not_found()
    await session.delete(organization)
    await session.commit()


@router.get("/{organization_id}/members")
async def list_members(
    organization_id: int, user: CurrentUser, session: SessionDep
) -> list[UserOut]:
    await get_visible_organization(session, user, organization_id)
    members = await session.scalars(
        select(User)
        .join(Membership)
        .where(Membership.organization_id == organization_id)
        .order_by(User.name)
    )
    return [UserOut.model_validate(member) for member in members]


@router.post("/{organization_id}/members", status_code=status.HTTP_204_NO_CONTENT)
async def add_member(
    organization_id: int, body: MemberAdd, _: Technician, session: SessionDep
) -> None:
    if await session.get(Organization, organization_id) is None:
        raise not_found()
    session.add(Membership(user_id=body.user_id, organization_id=organization_id))
    await session.commit()


@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    organization_id: int, user_id: int, _: Technician, session: SessionDep
) -> None:
    result = await session.execute(
        delete(Membership).where(
            Membership.organization_id == organization_id, Membership.user_id == user_id
        )
    )
    if result.rowcount == 0:
        raise not_found()
    await session.commit()
