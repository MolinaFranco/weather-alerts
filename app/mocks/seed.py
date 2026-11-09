"""Demo data: a few users, an organization with its points and some alerts.

Run with `python -m app.mocks.seed`. Does nothing if there are users already. Every demo
account uses the password `demo-password`.
"""

import asyncio
import logging

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionFactory, engine
from app.enums import DataStatus, EventType, Role
from app.models import Alert, MeasurementPoint, Membership, Organization, User

log = logging.getLogger(__name__)

PASSWORD = "demo-password"


async def seed() -> None:
    async with SessionFactory() as session:
        if await session.scalar(select(User.id).limit(1)) is not None:
            log.info("There is data already, nothing to seed")
            return

        password_hash = await hash_password(PASSWORD)

        def user(name, email, phone, role=Role.CLIENT):
            return User(name=name, email=email, phone=phone, password_hash=password_hash, role=role)

        admin = user("Admin", "admin@example.com", "+5493410000001", Role.ADMIN)
        technician = user("Técnico", "tecnico@example.com", "+5493410000002", Role.TECHNICIAN)
        ana = user("Ana Pérez", "ana@example.com", "+5493415550000")
        juan = user("Juan Gómez", "juan@example.com", "+5493415550001")
        estancia = Organization(name="Estancia La Esperanza")
        session.add_all([admin, technician, ana, juan, estancia])
        await session.flush()

        def point(name, latitude, longitude, status=DataStatus.ACTIVE, **owner):
            return MeasurementPoint(
                name=name, latitude=latitude, longitude=longitude, status=status, **owner
            )

        norte = point("Lote Norte", -33.12, -60.45, organization_id=estancia.id)
        sur = point("Lote Sur", -33.16, -60.47, organization_id=estancia.id)
        potrero = point(
            "Potrero Nuevo", -33.20, -60.50, DataStatus.TESTING, organization_id=estancia.id
        )
        quinta = point("Quinta de Juan", -32.95, -60.66, user_id=juan.id)
        session.add_all(
            [
                Membership(user_id=ana.id, organization_id=estancia.id),
                Membership(user_id=juan.id, organization_id=estancia.id),
                norte,
                sur,
                potrero,
                quinta,
            ]
        )
        await session.flush()

        session.add_all(
            [
                Alert(user_id=ana.id, point_id=norte.id, event_type=EventType.FROST, threshold=60),
                Alert(user_id=ana.id, point_id=sur.id, event_type=EventType.RAIN, threshold=70),
                Alert(user_id=juan.id, point_id=norte.id, event_type=EventType.FROST, threshold=40),
                Alert(user_id=juan.id, point_id=quinta.id, event_type=EventType.HAIL, threshold=50),
            ]
        )
        await session.commit()
        log.info("Seeded 4 users, 1 organization, 4 points and 4 alerts")


async def main() -> None:
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
