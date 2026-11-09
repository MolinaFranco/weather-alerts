"""Stands in for the real ingestion job, which already exists outside this project.

Like the real one, it upserts forecasts for every point, event and upcoming day, knowing
nothing about alerts or statuses. Run with `python -m app.mocks.fake_ingest`.
"""

import asyncio
import logging
import os
import random
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import SessionFactory, engine
from app.enums import EventType
from app.loop import local_today, run_until_stopped, stop_on_signals
from app.models import MeasurementPoint, WeatherForecast

log = logging.getLogger(__name__)

DAYS_AHEAD = 7
# A real feed revises only some forecasts on each update.
SHARE_REVISED = 0.5

_insert = insert(WeatherForecast)
UPSERT = _insert.on_conflict_do_update(
    index_elements=["point_id", "forecast_date", "event_type"],
    set_={"probability": _insert.excluded.probability},
)


def revise(previous: int | None) -> int | None:
    """A new probability, or None to leave the forecast as it is.

    The walk is pulled back towards 45%, so values wander and cross thresholds now and then
    instead of piling up at 0 or 100.
    """
    if previous is None:
        return random.randint(0, 60)
    if random.random() > SHARE_REVISED:
        return None
    return max(0, min(100, previous + random.randint(-18, 18) + (45 - previous) // 8))


async def current_probabilities(session: AsyncSession, days: list[date]) -> dict:
    rows = await session.execute(
        select(
            WeatherForecast.point_id,
            WeatherForecast.forecast_date,
            WeatherForecast.event_type,
            WeatherForecast.probability,
        ).where(WeatherForecast.forecast_date.in_(days))
    )
    return {(point, day, event): probability for point, day, event, probability in rows}


async def ingest() -> None:
    days = [local_today(settings.timezone) + timedelta(days=n) for n in range(DAYS_AHEAD)]
    async with SessionFactory() as session, session.begin():
        point_ids = (await session.scalars(select(MeasurementPoint.id))).all()
        current = await current_probabilities(session, days)
        rows = []
        for point_id in point_ids:
            for day in days:
                for event in EventType:
                    probability = revise(current.get((point_id, day, event)))
                    if probability is not None:
                        rows.append(
                            {
                                "point_id": point_id,
                                "forecast_date": day,
                                "event_type": event,
                                "probability": probability,
                            }
                        )
        if rows:
            # A list of rows runs as a batched executemany, whatever the number of points.
            await session.execute(UPSERT, rows)
    log.info("Updated %s forecasts for %s points", len(rows), len(point_ids))


async def main() -> None:
    interval = float(os.environ.get("INGEST_INTERVAL", "10"))
    await run_until_stopped(stop_on_signals(), ingest, interval, log)
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
