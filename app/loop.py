"""What the background processes (worker and fake ingestion) have in common."""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import date, datetime
from zoneinfo import ZoneInfo


def local_today(timezone: str) -> date:
    return datetime.now(ZoneInfo(timezone)).date()


def stop_on_signals() -> asyncio.Event:
    """Set on SIGTERM or SIGINT, so the loop can finish what it is doing and exit."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    return stop


async def run_until_stopped(
    stop: asyncio.Event,
    cycle: Callable[[], Awaitable[None]],
    interval: float,
    log: logging.Logger,
) -> None:
    while not stop.is_set():
        try:
            await cycle()
        except Exception as error:
            # One line per failure: a database restart would otherwise flood the logs with
            # the same traceback every interval. The full trace is there at debug level.
            log.error("Cycle failed, retrying in %s s: %r", interval, error)
            log.debug("Cycle failure", exc_info=True)
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
