"""Background job: evaluate alerts and send the notices that are due, every few seconds.

Run with `python -m app.worker`. Stops cleanly on SIGTERM, after the current cycle.
"""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db import SessionFactory
from app.jobs.dispatcher import dispatch
from app.jobs.evaluator import evaluate
from app.jobs.notifier import LogNotifier, Notifier

log = logging.getLogger(__name__)

BATCH_SIZE = 100


def local_today(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


async def run_cycle(sessions: async_sessionmaker[AsyncSession], notifier: Notifier) -> None:
    async with sessions() as session:
        async with session.begin():
            today = local_today(settings.timezone)
            created = await evaluate(session, today, settings.renotify_step)

        handled = 0
        while True:
            async with session.begin():
                batch = await dispatch(session, notifier, BATCH_SIZE)
            handled += batch
            if batch < BATCH_SIZE:
                break

    level = logging.INFO if created or handled else logging.DEBUG
    log.log(level, "Cycle done: %s new notices, %s handled", created, handled)


async def run_until_stopped(
    stop: asyncio.Event, cycle: Callable[[], Awaitable[None]], interval: float
) -> None:
    while not stop.is_set():
        try:
            await cycle()
        except Exception:
            log.exception("Cycle failed, retrying in %s s", interval)
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)

    notifier = LogNotifier()
    await run_until_stopped(
        stop, lambda: run_cycle(SessionFactory, notifier), settings.evaluation_interval
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
