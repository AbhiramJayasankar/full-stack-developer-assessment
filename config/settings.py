import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# Ephemeral local-only key; deployments must supply a stable secret.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or __import__("secrets").token_urlsafe(48)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "silk",
    "orders",
    "mailqueue",
]
MIDDLEWARE = ["silk.middleware.SilkyMiddleware"]
ROOT_URLCONF = "config.urls"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
STATIC_URL = "static/"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS = True
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 300}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {"visibility_timeout": 300}
CELERY_VISIBILITY_TIMEOUT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 25
CELERY_TASK_TIME_LIMIT = 30
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_DEFAULT_QUEUE = "emails"
CELERY_BEAT_SCHEDULE = {
    "recover-outbox": {"task": "mailqueue.tasks.dispatch_pending", "schedule": 10.0}
}
EMAIL_RATE_CAPACITY = 200
EMAIL_RATE_WINDOW_MS = 60_000
EMAIL_RATE_KEY = os.environ.get("EMAIL_RATE_KEY", "email:provider:sliding-window")
EMAIL_PROVIDER_URL = os.environ.get("EMAIL_PROVIDER_URL", "")
