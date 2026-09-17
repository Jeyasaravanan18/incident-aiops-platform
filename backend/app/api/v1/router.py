from fastapi import APIRouter

from app.api.v1 import (
    ai,
    alerts,
    analytics,
    auth,
    incidents,
    logs,
    notifications,
    postmortems,
    runbooks,
    services,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(services.router)
api_router.include_router(alerts.router)
api_router.include_router(incidents.router)
api_router.include_router(logs.router)
api_router.include_router(runbooks.router)
api_router.include_router(postmortems.router)
api_router.include_router(notifications.router)
api_router.include_router(ai.router)
api_router.include_router(analytics.router)
