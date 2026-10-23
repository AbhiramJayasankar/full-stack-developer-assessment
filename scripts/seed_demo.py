import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from orders.models import Customer, Order

if not Order.objects.exists():
    customer = Customer.objects.create(name="Demo customer")
    Order.objects.bulk_create([Order(customer=customer, total="19.95") for _ in range(250)])
print(f"{Order.objects.count()} demo orders ready")
