from django.http import JsonResponse
from .models import Order


def render_summary(orders):
    return JsonResponse(
        {
            "orders": [
                {"id": o.pk, "customer": o.customer_label, "total": str(o.total)} for o in orders
            ]
        }
    )


def broken_summary(request):
    """Local diagnostic reproduction, intentionally exhibits N+1 queries."""
    return render_summary(Order.objects.order_by("pk"))


def summary(request):
    return render_summary(Order.objects.select_related("customer").order_by("pk"))
