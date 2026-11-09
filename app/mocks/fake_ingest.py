"""Stands in for the real ingestion job, which already exists outside this project.

Every few seconds it writes a forecast for each point, each event and each of the next
seven days, the way the real job would: plain upserts that know nothing about alerts or
statuses. Probabilities drift a little on every pass, so thresholds get crossed now and
then and the worker has something to notify. Run with `python -m app.mocks.fake_ingest`.
"""

import asyncio
import logging
import os
import random
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.db import SessionFactory, engine
from app.enums import EventType
from app.models import MeasurementPoint, WeatherForecast
from app.worker import local_today, run_until_stopped, stop_on_signals

log = logging.getLogger(__name__)

DAYS_AHEAD = 7
INTERVAL = float(os.environ.get("INGEST_INTERVAL", "10"))


def drift(previous: int | None) -> int:
    if previous is None:
        return random.randint(0, 60)
    return max(0, min(100, previous + random.randint(-12, 15)))


async def ingest() -> None:
    days = [local_today(settings.timezone) + timedelta(days=n) for n in range(DAYS_AHEAD)]
    async with SessionFactory() as session, session.begin():
        point_ids = (await session.scalars(select(MeasurementPoint.id))).all()
        current = await session.execute(
            select(
                WeatherForecast.point_id,
                WeatherForecast.forecast_date,
                WeatherForecast.event_type,
                WeatherForecast.probability,
            ).where(WeatherForecast.forecast_date.in_(days))
        )
        previous = {(point, day, event): probability for point, day, event, probability in current}

        rows = [
            {
                "point_id": point_id,
                "forecast_date": day,
                "event_type": event,
                "probability": drift(previous.get((point_id, day, event))),
            }
            for point_id in point_ids
            for day in days
            for event in EventType
        ]
        if not rows:
            return
        statement = insert(WeatherForecast).values(rows)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=["point_id", "forecast_date", "event_type"],
                set_={"probability": statement.excluded.probability},
            )
        )
    log.info("Wrote %s forecasts for %s points", len(rows), len(point_ids))


async def main() -> None:
    await run_until_stopped(stop_on_signals(), ingest, INTERVAL)
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
