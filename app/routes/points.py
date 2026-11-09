from datetime import date

from fastapi import APIRouter, status
from sqlalchemy import select

from app.access import get_visible_point, not_found, visible_points
from app.auth import Admin, CurrentUser, Technician, is_staff
from app.db import SessionDep
from app.enums import DataStatus
from app.models import MeasurementPoint, WeatherForecast
from app.schemas import ForecastOut, ForecastUpdate, PointCreate, PointOut, PointUpdate

router = APIRouter(tags=["points"])


@router.get("/points")
async def list_points(user: CurrentUser, session: SessionDep) -> list[PointOut]:
    points = await session.scalars(visible_points(user).order_by(MeasurementPoint.name))
    return [PointOut.model_validate(point) for point in points]


@router.post("/points", status_code=status.HTTP_201_CREATED)
async def create_point(body: PointCreate, _: Technician, session: SessionDep) -> PointOut:
    point = MeasurementPoint(**body.model_dump())
    session.add(point)
    await session.commit()
    await session.refresh(point)
    return PointOut.model_validate(point)


@router.patch("/points/{point_id}")
async def update_point(
    point_id: int, body: PointUpdate, _: Technician, session: SessionDep
) -> PointOut:
    point = await session.get(MeasurementPoint, point_id)
    if point is None:
        raise not_found()
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(point, field, value)
    await session.commit()
    return PointOut.model_validate(point)


@router.delete("/points/{point_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_point(point_id: int, _: Admin, session: SessionDep) -> None:
    point = await session.get(MeasurementPoint, point_id)
    if point is None:
        raise not_found()
    await session.delete(point)
    await session.commit()


@router.get("/points/{point_id}/forecasts")
async def list_forecasts(
    point_id: int,
    user: CurrentUser,
    session: SessionDep,
    since: date | None = None,
    until: date | None = None,
) -> list[ForecastOut]:
    """A point's samples, by day. Clients only get active ones."""
    await get_visible_point(session, user, point_id)
    query = select(WeatherForecast).where(WeatherForecast.point_id == point_id)
    if not is_staff(user):
        query = query.where(WeatherForecast.status == DataStatus.ACTIVE)
    if since:
        query = query.where(WeatherForecast.forecast_date >= since)
    if until:
        query = query.where(WeatherForecast.forecast_date <= until)
    forecasts = await session.scalars(
        query.order_by(WeatherForecast.forecast_date, WeatherForecast.event_type)
    )
    return [ForecastOut.model_validate(forecast) for forecast in forecasts]


@router.patch("/forecasts/{forecast_id}")
async def mark_forecast(
    forecast_id: int, body: ForecastUpdate, _: Technician, session: SessionDep
) -> ForecastOut:
    """Mark a single sample, e.g. an anomalous reading, as testing or disabled."""
    forecast = await session.get(WeatherForecast, forecast_id)
    if forecast is None:
        raise not_found()
    forecast.status = body.status
    await session.commit()
    # The status trigger keeps samples of a point that isn't active in the point's status.
    await session.refresh(forecast)
    return ForecastOut.model_validate(forecast)


@router.delete("/forecasts/{forecast_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_forecast(forecast_id: int, _: Admin, session: SessionDep) -> None:
    forecast = await session.get(WeatherForecast, forecast_id)
    if forecast is None:
        raise not_found()
    await session.delete(forecast)
    await session.commit()
