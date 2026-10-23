import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse
import os
import uuid

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from mailqueue.services import enqueue_email

parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, default=500)
args = parser.parse_args()
batch = uuid.uuid4()
for i in range(args.count):
    enqueue_email(
        idempotency_key=f"{batch}:{i}",
        recipient="demo@example.com",
        subject=f"Order {i}",
        body="Thank you",
    )
print(f"Accepted {args.count} jobs; batch={batch}")
