from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text
from starlette.responses import Response

from app.api.v1.router import api_router
from app.api.v1.websockets import router as websocket_router
from app.core.config import settings
from app.core.database import engine, get_database, get_mongo_client, init_db_indexes
from app.core.errors import AppError, app_error_handler
from app.core.middleware import RequestIDMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db_indexes()
    except Exception:
        pass
    yield
    try:
        client = get_mongo_client()
        client.close()
    except Exception:
        pass


app = FastAPI(
    title="Production Incident Management & AIOps Platform",
    version="0.1.0",
    description=(
        "SRE incident management platform with alerting, AI assistance, "
        "and real-time operations."
    ),
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(AppError, app_error_handler)
app.include_router(api_router)
app.include_router(websocket_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    db_status = "offline"
    try:
        db = get_database()
        await db.command("ping")
        db_status = "connected"
    except Exception:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("select 1"))
            db_status = "connected"
        except Exception:
            pass

    redis_status = "offline"
    try:
        redis = Redis.from_url(settings.redis_url)
        await redis.ping()
        await redis.aclose()
        redis_status = "connected"
    except Exception:
        pass
    return {"status": "ready", "database": db_status, "redis": redis_status}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
