from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import BackgroundTasks

from app.core.config import settings

logger = logging.getLogger(__name__)


def enqueue_task(
    background_tasks: BackgroundTasks,
    task_name: str,
    fallback: Callable[..., Any],
    *args: Any,
) -> str:
    if settings.job_queue_backend == "celery":
        try:
            from app.worker import celery_app

            celery_app.send_task(task_name, args=list(args))
            return "celery"
        except Exception as exc:
            logger.warning("Celery kuyruğuna gönderilemedi, satır içi çalıştırılıyor: %s", exc)
    background_tasks.add_task(fallback, *args)
    return "inline"
