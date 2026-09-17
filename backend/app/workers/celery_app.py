from celery import Celery

from app.core.config import settings

celery_app = Celery("incident_aiops", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_routes = {"app.workers.tasks.*": {"queue": "incident-aiops"}}
celery_app.conf.beat_schedule = {
    "monitor-services-every-30-seconds": {
        "task": "app.workers.tasks.monitor_services",
        "schedule": 30.0,
    },
    "cleanup-health-history-daily": {
        "task": "app.workers.tasks.cleanup_health_history",
        "schedule": 86400.0,
    },
}
