"""Background job: evaluate alerts and send the notices that are due, periodically.

Run with `python -m app.worker`. Stops cleanly on SIGTERM, between notices.
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db import SessionFactory, engine
from app.jobs.dispatcher import dispatch_next
from app.jobs.evaluator import evaluate
from app.jobs.notifier import LogNotifier, Notifier
from app.loop import local_today, run_until_stopped, stop_on_signals

log = logging.getLogger(__name__)


async def run_cycle(
    sessions: async_sessionmaker[AsyncSession], notifier: Notifier, stop: asyncio.Event
) -> None:
    today = local_today(settings.timezone)
    async with sessions() as session:
        async with session.begin():
            queued = await evaluate(session, today, settings.renotify_step)

        # One notice per transaction, checking for shutdown in between, so stopping the
        # worker never leaves more than one message half done.
        handled = 0
        while not stop.is_set():
            async with session.begin():
                if not await dispatch_next(session, notifier, today):
                    break
            handled += 1

    level = logging.INFO if queued or handled else logging.DEBUG
    log.log(level, "Cycle done: %s notices queued, %s handled", queued, handled)


async def main() -> None:
    stop = stop_on_signals()
    notifier = LogNotifier()
    await run_until_stopped(
        stop, lambda: run_cycle(SessionFactory, notifier, stop), settings.evaluation_interval, log
    )
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
