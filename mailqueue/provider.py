import requests
from django.conf import settings
from .models import Delivery


class TransientProviderError(Exception):
    pass


class PermanentProviderError(Exception):
    pass


def send(job):
    if not settings.EMAIL_PROVIDER_URL:
        # Safe local demo; no actual email is sent.
        Delivery.objects.get_or_create(job=job)
        return
    try:
        response = requests.post(
            settings.EMAIL_PROVIDER_URL,
            json={"to": job.recipient, "subject": job.subject, "body": job.body},
            headers={"Idempotency-Key": str(job.pk)},
            timeout=(3, 10),
        )
    except requests.RequestException as exc:
        raise TransientProviderError(type(exc).__name__) from exc
    if response.status_code == 429 or response.status_code >= 500:
        raise TransientProviderError(f"Provider HTTP {response.status_code}")
    if not 200 <= response.status_code < 300:
        raise PermanentProviderError(f"Provider HTTP {response.status_code}")
