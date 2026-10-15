"""Celery application and asynchronous analytics background worker.

Configured with:
- Redis as message broker and result backend
- acks_late=True (tasks are acknowledged only after completion)
- worker_prefetch_multiplier=1 (fair task distribution)
- CELERY_ALWAYS_EAGER support for testing
"""

import logging

from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "url_shortener",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_always_eager=settings.CELERY_ALWAYS_EAGER,
    task_eager_propagates=True,
)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="app.worker.record_click",
)
def record_click(
    self,
    link_id: int,
    client_ip: str,
    user_agent_str: str,
    referrer: str,
    clicked_at_iso: str,
) -> None:
    """Background task to record analytics click event."""
    from app.services.analytics import process_click_event
    try:
        process_click_event(
            link_id=link_id,
            client_ip=client_ip,
            user_agent_str=user_agent_str,
            referrer=referrer,
            clicked_at_iso=clicked_at_iso,
        )
    except Exception as exc:
        logger.error(f"Error processing click event for link {link_id}: {exc}")
        raise self.retry(exc=exc) from exc
