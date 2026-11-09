"""What each user can see, and the 404 for everything else."""

from fastapi import HTTPException, status
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import is_staff
from app.enums import DataStatus
from app.models import MeasurementPoint, Membership, Organization, User


def my_organization_ids(user: User) -> Select:
    return select(Membership.organization_id).where(Membership.user_id == user.id)


def visible_organizations(user: User) -> Select:
    query = select(Organization)
    if is_staff(user):
        return query
    return query.where(Organization.id.in_(my_organization_ids(user)))


def visible_points(user: User) -> Select:
    """Staff see every point; clients see their own and their organizations', when active."""
    query = select(MeasurementPoint)
    if is_staff(user):
        return query
    return query.where(
        MeasurementPoint.status == DataStatus.ACTIVE,
        or_(
            MeasurementPoint.user_id == user.id,
            MeasurementPoint.organization_id.in_(my_organization_ids(user)),
        ),
    )


def not_found() -> HTTPException:
    # Also used for things that exist but aren't yours, so ids can't be probed.
    return HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


async def get_or_404[T](session: AsyncSession, model: type[T], item_id: int) -> T:
    item = await session.get(model, item_id)
    if item is None:
        raise not_found()
    return item


async def get_visible_point(session: AsyncSession, user: User, point_id: int) -> MeasurementPoint:
    point = await session.scalar(visible_points(user).where(MeasurementPoint.id == point_id))
    if point is None:
        raise not_found()
    return point


async def get_visible_organization(
    session: AsyncSession, user: User, organization_id: int
) -> Organization:
    query = visible_organizations(user).where(Organization.id == organization_id)
    organization = await session.scalar(query)
    if organization is None:
        raise not_found()
    return organization
