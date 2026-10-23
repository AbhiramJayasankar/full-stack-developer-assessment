"""Capture actual Silk SQL records; never substitute estimated query counts."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.test import Client
from orders.models import Customer, Order
from silk.models import Request

if not Order.objects.exists():
    customer = Customer.objects.create(name="Demo customer")
    Order.objects.bulk_create([Order(customer=customer, total="19.95") for _ in range(250)])
client = Client()
report = {"order_count": Order.objects.count(), "source": "django-silk Request.queries"}
for label, path in [("before", "/demo/orders/broken/"), ("after", "/api/orders/summary/")]:
    response = client.get(path)
    assert response.status_code == 200
    request = Request.objects.filter(path=path).latest("start_time")
    queries = list(request.queries.all())
    report[label] = {
        "path": path,
        "query_count": len(queries),
        "sql_examples": [q.query for q in queries[:2]],
    }
assert report["before"]["query_count"] == report["order_count"] + 1
assert report["after"]["query_count"] == 1
output = Path(__file__).resolve().parents[1] / "evidence" / "silk-queries.json"
output.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
