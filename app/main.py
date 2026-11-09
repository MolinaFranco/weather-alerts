from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionDep

app = FastAPI(title="Weather Alerts")


@app.get("/health")
async def health(session: SessionDep) -> dict[str, str]:
    # asyncpg raises plain OSError subclasses when it can't reach the server.
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok"}
