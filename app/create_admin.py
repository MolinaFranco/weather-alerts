"""Create the first admin, who can then promote other users through the API.

Usage: python -m app.create_admin "Name" email phone   (the password is asked for)
"""

import asyncio
import getpass
import sys

from app.auth import passwords
from app.db import SessionFactory, engine
from app.enums import Role
from app.models import User


async def create_admin(name: str, email: str, phone: str, password: str) -> None:
    async with SessionFactory() as session:
        session.add(
            User(
                name=name,
                email=email.lower(),
                phone=phone,
                password_hash=passwords.hash(password),
                role=Role.ADMIN,
            )
        )
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    password = getpass.getpass("Password: ")
    if len(password) < 8:
        sys.exit("The password needs at least 8 characters.")
    asyncio.run(create_admin(*sys.argv[1:], password))
    print("Admin created.")
