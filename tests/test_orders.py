import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import RequestFactory
from orders.models import Customer, Order
from orders.views import summary, broken_summary
from silk.models import Request


@pytest.mark.django_db
def test_query_regression_and_silk_evidence(client):
    customer = Customer.objects.create(name="Alice")
    Order.objects.bulk_create([Order(customer=customer, total="12.50") for _ in range(250)])
    factory = RequestFactory()
    with CaptureQueriesContext(connection) as before:
        broken = broken_summary(factory.get("/"))
    with CaptureQueriesContext(connection) as after:
        fixed = summary(factory.get("/"))
    assert len(before) == 251
    assert len(after) == 1
    assert broken.content == fixed.content
    for path, count in [("/demo/orders/broken/", 251), ("/api/orders/summary/", 1)]:
        assert client.get(path).status_code == 200
        recorded = Request.objects.filter(path=path).latest("start_time")
        assert recorded.queries.count() == count
