"""Demo data: a few users, an organization with its points and some alerts.

Run with `python -m app.mocks.seed`. Does nothing if there are users already. Every demo
account uses the password `demo-password`.
"""

import asyncio
import logging

from sqlalchemy import select

from app.auth import hash_password
from app.db import SessionFactory, engine
from app.enums import EventType, OperationalStatus, Role
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

        admin = user("Admin", "admin@example.com", "+5493410000100", Role.ADMIN)
        technician = user("Técnico", "tecnico@example.com", "+5493410000200", Role.TECHNICIAN)
        ana = user("Ana Pérez", "ana@example.com", "+5493415550301")
        juan = user("Juan Gómez", "juan@example.com", "+5493415550402")
        estancia = Organization(name="Estancia La Esperanza")
        session.add_all([admin, technician, ana, juan, estancia])
        await session.flush()

        norte = MeasurementPoint(
            name="Lote Norte", latitude=-33.12, longitude=-60.45, organization_id=estancia.id
        )
        sur = MeasurementPoint(
            name="Lote Sur", latitude=-33.16, longitude=-60.47, organization_id=estancia.id
        )
        potrero = MeasurementPoint(
            name="Potrero Nuevo",
            latitude=-33.20,
            longitude=-60.50,
            organization_id=estancia.id,
            status=OperationalStatus.TESTING,
        )
        quinta = MeasurementPoint(
            name="Quinta de Juan", latitude=-32.95, longitude=-60.66, user_id=juan.id
        )
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

        def alert(user, point, event_type, threshold):
            return Alert(
                user_id=user.id, point_id=point.id, event_type=event_type, threshold=threshold
            )

        session.add_all(
            [
                alert(ana, norte, EventType.FROST, 60),
                alert(ana, sur, EventType.RAIN, 70),
                # Stays silent until a technician activates the point.
                alert(ana, potrero, EventType.RAIN, 50),
                alert(juan, norte, EventType.FROST, 40),
                alert(juan, quinta, EventType.HAIL, 50),
                # Staff hear about any point, even one they are not a member of.
                alert(technician, quinta, EventType.STRONG_WIND, 45),
            ]
        )
        await session.commit()
        log.info("Demo data loaded")


async def main() -> None:
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    asyncio.run(main())
