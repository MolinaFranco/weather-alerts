from enum import StrEnum


class Role(StrEnum):
    CLIENT = "client"
    TECHNICIAN = "technician"
    ADMIN = "admin"


class OperationalStatus(StrEnum):
    ACTIVE = "active"
    TESTING = "testing"
    DISABLED = "disabled"


class EventType(StrEnum):
    FROST = "frost"
    RAIN = "rain"
    HAIL = "hail"
    STRONG_WIND = "strong_wind"
    HEAT_WAVE = "heat_wave"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    # For a provider that can tell a permanent error; the log notifier never needs it.
    FAILED = "failed"
    SKIPPED = "skipped"
