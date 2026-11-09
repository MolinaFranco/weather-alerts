from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.enums import DataStatus, EventType, NotificationStatus, Role

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Phone = Annotated[str, StringConstraints(pattern=r"^\+[1-9][0-9]{7,14}$")]
Percentage = Annotated[int, Field(ge=1, le=100)]


class Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    name: Name
    email: EmailStr
    phone: Phone
    password: Annotated[str, Field(min_length=8, max_length=128)]


class StaffUserCreate(UserCreate):
    organization_ids: list[int] = []


class UserRoleUpdate(BaseModel):
    role: Role


class UserOut(Response):
    id: int
    name: str
    email: str
    phone: str
    role: Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OrganizationCreate(BaseModel):
    name: Name
    member_ids: list[int] = []


class OrganizationUpdate(BaseModel):
    name: Name


class OrganizationOut(Response):
    id: int
    name: str


class Me(UserOut):
    organizations: list[OrganizationOut]


class MemberAdd(BaseModel):
    user_id: int


class PointCreate(BaseModel):
    name: Name
    latitude: Annotated[Decimal, Field(ge=-90, le=90)]
    longitude: Annotated[Decimal, Field(ge=-180, le=180)]
    organization_id: int | None = None
    user_id: int | None = None

    @model_validator(mode="after")
    def single_owner(self) -> Self:
        if (self.organization_id is None) == (self.user_id is None):
            raise ValueError("a point belongs to exactly one of organization_id or user_id")
        return self


class PointUpdate(BaseModel):
    name: Name | None = None
    latitude: Annotated[Decimal, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[Decimal, Field(ge=-180, le=180)] | None = None
    status: DataStatus | None = None


class PointOut(Response):
    id: int
    name: str
    latitude: float
    longitude: float
    organization_id: int | None
    user_id: int | None
    status: DataStatus


class ForecastOut(Response):
    id: int
    forecast_date: date
    event_type: EventType
    probability: int
    status: DataStatus


class ForecastUpdate(BaseModel):
    status: DataStatus


class AlertCreate(BaseModel):
    point_id: int
    event_type: EventType
    threshold: Percentage


class AlertUpdate(BaseModel):
    threshold: Percentage | None = None
    is_active: bool | None = None


class AlertOut(Response):
    id: int
    point_id: int
    event_type: EventType
    threshold: int
    is_active: bool


class NotificationOut(Response):
    id: int
    alert_id: int
    forecast_date: date
    probability: int
    status: NotificationStatus
    created_at: datetime
    sent_at: datetime | None
