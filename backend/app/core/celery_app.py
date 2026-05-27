import os

from celery import Celery

celery_app = Celery(
    "finsight",
    broker=os.environ["CELERY_BROKER_URL"],
    backend=os.environ["CELERY_RESULT_BACKEND"],
    include=["app.tasks.market", "app.tasks.ai_tasks"],
)