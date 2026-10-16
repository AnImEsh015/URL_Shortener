"""Celery application and asynchronous analytics background worker.

Configured with:
- Redis / Render Key Value as message broker and result backend (with rediss:// TLS support)
- Database 0 safe: namespaced queue and result prefixes prevent collisions with application keys
- acks_late=True (tasks are acknowledged only after completion)
- worker_prefetch_multiplier=1 (fair task distribution)
- CELERY_ALWAYS_EAGER support for testing
"""

import logging
from typing import Any

from celery import Celery

from app.config import settings

logger = logging.getLogger(__name__)

broker_url = settings.CELERY_BROKER_URL or settings.REDIS_URL
backend_url = settings.CELERY_RESULT_BACKEND or settings.REDIS_URL

celery_app = Celery(
    "url_shortener",
    broker=broker_url,
    backend=backend_url,
)

celery_config: dict[str, Any] = {
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    "worker_prefetch_multiplier": 1,
    "task_always_eager": settings.CELERY_ALWAYS_EAGER,
    "task_eager_propagates": True,
    # Explicit namespacing ensures Celery and app keys never collide when sharing database 0
    "task_default_queue": "celery_queue",
    "result_key_prefix": "celery_task_result_",
}

# Render Key Value TLS support
if broker_url.startswith("rediss://"):
    celery_config["broker_use_ssl"] = {"ssl_cert_reqs": None}
if backend_url.startswith("rediss://"):
    celery_config["redis_backend_use_ssl"] = {"ssl_cert_reqs": None}

celery_app.conf.update(**celery_config)


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
