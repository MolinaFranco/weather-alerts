from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.db import SessionDep
from app.routes import alerts, auth, notifications, organizations, points, users

app = FastAPI(title="Weather Alerts")

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

for module in (auth, users, organizations, points, alerts, notifications):
    app.include_router(module.router)


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    # The database enforces uniqueness and references, so routes don't check them first
    # (a check before the insert would race anyway). Duplicates are conflicts; a missing
    # referenced row or a broken rule is a bad request.
    if exc.orig.sqlstate == "23505":
        return JSONResponse({"detail": "Already exists"}, status.HTTP_409_CONFLICT)
    return JSONResponse(
        {"detail": "Refers to something that doesn't exist or breaks a rule"},
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.get("/health")
async def health(session: SessionDep) -> dict[str, str]:
    # asyncpg raises plain OSError subclasses when it can't reach the server.
    try:
        await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable") from exc
    return {"status": "ok"}
