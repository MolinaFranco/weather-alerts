"""Create the first admin, who can then promote other users through the API.

Usage: python -m app.create_admin "Name" email phone   (the password is asked for)
"""

import asyncio
import getpass
import sys

from pydantic import ValidationError

from app.auth import hash_password
from app.db import SessionFactory, engine
from app.enums import Role
from app.models import User
from app.schemas import UserCreate


async def create_admin(admin: UserCreate) -> None:
    async with SessionFactory() as session:
        session.add(
            User(
                name=admin.name,
                email=admin.email,
                phone=admin.phone,
                password_hash=await hash_password(admin.password),
                role=Role.ADMIN,
            )
        )
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    name, email, phone = sys.argv[1:]
    try:
        admin = UserCreate(name=name, email=email, phone=phone, password=getpass.getpass())
    except ValidationError as error:
        sys.exit(str(error))
    asyncio.run(create_admin(admin))
    print("Admin created.")
