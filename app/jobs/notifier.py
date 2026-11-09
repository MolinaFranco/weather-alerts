import logging
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.enums import EventType

log = logging.getLogger(__name__)

EVENT_NAMES = {
    EventType.FROST: "helada",
    EventType.RAIN: "lluvia",
    EventType.HAIL: "granizo",
    EventType.STRONG_WIND: "viento fuerte",
    EventType.HEAT_WAVE: "ola de calor",
}


@dataclass(frozen=True)
class Notice:
    phone: str
    point_name: str
    event_type: EventType
    forecast_date: date
    probability: int

    @property
    def message(self) -> str:
        return (
            f"Alerta de {EVENT_NAMES[self.event_type]} en {self.point_name}: "
            f"{self.probability}% de probabilidad para el {self.forecast_date:%d/%m}."
        )


class Notifier(Protocol):
    async def send(self, notice: Notice) -> None: ...


class LogNotifier:
    """Stands in for the WhatsApp client, which is out of scope."""

    async def send(self, notice: Notice) -> None:
        log.info("To %s: %s", notice.phone, notice.message)
