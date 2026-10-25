"""A deliberately tiny job seam. No broker, no Celery.

Register a callable with ``@job("name")`` in any app's ``jobs.py``; run jobs with
``python manage.py runjobs`` from cron, a Cloud Scheduler hit, or a loop.
Swap in Celery/RQ later by calling the same functions from your task wrapper.
"""

import logging
from collections.abc import Callable

from django.utils.module_loading import autodiscover_modules

logger = logging.getLogger(__name__)

JobFunc = Callable[[], object]
_REGISTRY: dict[str, JobFunc] = {}


def job(name: str) -> Callable[[JobFunc], JobFunc]:
    """Decorator registering ``func`` under ``name``."""

    def decorator(func: JobFunc) -> JobFunc:
        if name in _REGISTRY and _REGISTRY[name] is not func:
            raise ValueError(f"Job {name!r} is already registered")
        _REGISTRY[name] = func
        return func

    return decorator


def registered_jobs() -> dict[str, JobFunc]:
    autodiscover_modules("jobs")
    return dict(_REGISTRY)


def run_job(name: str) -> bool:
    """Run one job; log and return False on failure instead of raising."""
    func = registered_jobs()[name]
    try:
        func()
    except Exception:
        logger.exception("Job %s failed", name)
        return False
    logger.info("Job %s finished", name)
    return True
