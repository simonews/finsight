import os

from celery import Celery
from celery.signals import setup_logging as setup_logging_signal

from app.core.logging_config import setup_logging

celery_app = Celery(
    "finsight",
    broker=os.environ["CELERY_BROKER_URL"],
    backend=os.environ["CELERY_RESULT_BACKEND"],
    include=["app.tasks.market", "app.tasks.ai_tasks"],
)


@setup_logging_signal.connect
def _configure_celery_logging(**kwargs) -> None:
    setup_logging()