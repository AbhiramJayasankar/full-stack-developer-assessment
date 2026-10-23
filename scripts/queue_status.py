"""Print job counts without displaying recipients or email bodies."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.db.models import Count, Sum
from mailqueue.models import DeadLetter, Delivery, EmailJob

print("Jobs by state:", list(EmailJob.objects.values("state").annotate(count=Count("id"))))
print("Provider failures:", EmailJob.objects.aggregate(total=Sum("failures"))["total"] or 0)
print("Durable deliveries:", Delivery.objects.count())
print("Dead letters:", DeadLetter.objects.count())
