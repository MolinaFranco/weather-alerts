from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.enums import DataStatus, EventType, NotificationStatus, Role


def pg_enum(enum: type[StrEnum], name: str) -> Enum:
    # Store the lowercase values, not the member names.
    return Enum(enum, name=name, values_callable=lambda members: [m.value for m in members])


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(pg_enum(Role, "user_role"), server_default=Role.CLIENT)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class MeasurementPoint(Base):
    """Owned by either an organization or a single user, never both."""

    __tablename__ = "measurement_points"
    __table_args__ = (
        CheckConstraint("num_nonnulls(organization_id, user_id) = 1", name="single_owner"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        UniqueConstraint("organization_id", "name"),
        UniqueConstraint("user_id", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    status: Mapped[DataStatus] = mapped_column(
        pg_enum(DataStatus, "data_status"), server_default=DataStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WeatherForecast(Base):
    """A sample written by the ingestion job: one event probability for one day at one point."""

    __tablename__ = "weather_forecasts"
    __table_args__ = (
        UniqueConstraint("point_id", "forecast_date", "event_type"),
        CheckConstraint("probability BETWEEN 0 AND 100", name="probability_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    point_id: Mapped[int] = mapped_column(ForeignKey("measurement_points.id", ondelete="CASCADE"))
    forecast_date: Mapped[date] = mapped_column(Date)
    event_type: Mapped[EventType] = mapped_column(pg_enum(EventType, "event_type"))
    probability: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[DataStatus] = mapped_column(
        pg_enum(DataStatus, "data_status"), server_default=DataStatus.ACTIVE
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("user_id", "point_id", "event_type"),
        CheckConstraint("threshold BETWEEN 1 AND 100", name="threshold_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    point_id: Mapped[int] = mapped_column(ForeignKey("measurement_points.id", ondelete="CASCADE"))
    event_type: Mapped[EventType] = mapped_column(pg_enum(EventType, "event_type"))
    threshold: Mapped[int] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # One row per alert, day and probability level makes evaluation idempotent.
        UniqueConstraint("alert_id", "forecast_date", "probability"),
        Index("ix_notifications_pending", "id", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"))
    forecast_date: Mapped[date] = mapped_column(Date)
    probability: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum(NotificationStatus, "notification_status"),
        server_default=NotificationStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    sent_at: Mapped[datetime | None]
