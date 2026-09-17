from app.workers.celery_app import celery_app
from app.workers.tasks import cleanup_health_history, monitor_services, run_ai_analysis


def test_celery_task_registration() -> None:
    assert monitor_services.name == "app.workers.tasks.monitor_services"
    assert run_ai_analysis.name == "app.workers.tasks.run_ai_analysis"
    assert cleanup_health_history.name == "app.workers.tasks.cleanup_health_history"


def test_celery_retry_configuration() -> None:
    # Auto retry for network and transient failures with exponential backoff
    assert monitor_services.autoretry_for == (Exception,)
    assert monitor_services.retry_backoff is True
    assert monitor_services.max_retries == 3


def test_celery_beat_schedule_configured() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "monitor-services-every-30-seconds" in schedule
    assert schedule["monitor-services-every-30-seconds"]["schedule"] == 30.0
    assert "cleanup-health-history-daily" in schedule
