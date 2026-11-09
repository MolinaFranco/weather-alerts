from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from fastapi import Path
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from app.enums import DataStatus, EventType, NotificationStatus, Role

# Postgres integer columns stop at 2**31 - 1; a bigger id would otherwise be a 500.
MAX_ID = 2**31 - 1
Id = Annotated[int, Field(ge=1, le=MAX_ID)]
PathId = Annotated[int, Path(ge=1, le=MAX_ID)]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Email = Annotated[EmailStr, AfterValidator(str.lower)]
Phone = Annotated[str, StringConstraints(pattern=r"^\+[1-9][0-9]{7,14}$")]
Password = Annotated[str, Field(min_length=8, max_length=128)]
Percentage = Annotated[int, Field(ge=1, le=100)]
Latitude = Annotated[Decimal, Field(ge=-90, le=90)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180)]


class FromOrm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    name: Name
    email: Email
    phone: Phone
    password: Password


class StaffUserCreate(UserCreate):
    organization_ids: list[Id] = []


class UserRoleUpdate(BaseModel):
    role: Role


class UserOut(FromOrm):
    id: int
    name: str
    email: str
    phone: str
    role: Role


class MemberOut(FromOrm):
    """What members of an organization see of each other: no contact details."""

    id: int
    name: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrganizationCreate(BaseModel):
    name: Name
    member_ids: list[Id] = []


class OrganizationUpdate(BaseModel):
    name: Name


class OrganizationOut(FromOrm):
    id: int
    name: str


class Me(UserOut):
    organizations: list[OrganizationOut]


class MemberAdd(BaseModel):
    user_id: Id


class PointCreate(BaseModel):
    name: Name
    latitude: Latitude
    longitude: Longitude
    organization_id: Id | None = None
    user_id: Id | None = None

    @model_validator(mode="after")
    def single_owner(self) -> Self:
        if (self.organization_id is None) == (self.user_id is None):
            raise ValueError("a point belongs to exactly one of organization_id or user_id")
        return self


class PointUpdate(BaseModel):
    name: Name | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    status: DataStatus | None = None


class PointOut(FromOrm):
    id: int
    name: str
    latitude: float
    longitude: float
    organization_id: int | None
    user_id: int | None
    status: DataStatus


class ForecastOut(FromOrm):
    id: int
    forecast_date: date
    event_type: EventType
    probability: int
    status: DataStatus


class ForecastUpdate(BaseModel):
    status: DataStatus


class AlertCreate(BaseModel):
    point_id: Id
    event_type: EventType
    threshold: Percentage


class AlertUpdate(BaseModel):
    threshold: Percentage | None = None
    is_active: bool | None = None


class AlertOut(FromOrm):
    id: int
    point_id: int
    event_type: EventType
    threshold: int
    is_active: bool


class NotificationOut(FromOrm):
    id: int
    alert_id: int
    forecast_date: date
    probability: int
    status: NotificationStatus
    created_at: datetime
    sent_at: datetime | None
