"""Analytics aggregations for the dashboard and analytics page."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from .models import (
    ApprovalRequest,
    GoodsReceiptNote,
    Payment,
    PurchaseOrder,
    PurchaseOrderLine,
    RequestForQuotation,
    Vendor,
    VendorBill,
)

_ZERO = Decimal("0.00")
_DEC = DecimalField(max_digits=18, decimal_places=2)


def monthly_spend(months: int = 6):
    """Committed PO value grouped by month, most recent ``months`` window."""
    qs = (
        PurchaseOrder.objects.exclude(
            status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED])
        .annotate(m=TruncMonth("order_date"))
        .values("m")
        .annotate(total=Coalesce(Sum("total"), Value(_ZERO), output_field=_DEC))
        .order_by("m")
    )
    rows = [{"month": r["m"], "total": r["total"]} for r in qs if r["m"]]
    return rows[-months:]


def top_suppliers(limit: int = 5):
    qs = (
        PurchaseOrder.objects.exclude(
            status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED])
        .values("vendor__name")
        .annotate(total=Coalesce(Sum("total"), Value(_ZERO), output_field=_DEC),
                  orders=Count("id"))
        .order_by("-total")[:limit]
    )
    return [{"vendor": r["vendor__name"], "total": r["total"], "orders": r["orders"]} for r in qs]


def category_spend():
    qs = (
        PurchaseOrderLine.objects.exclude(
            purchase_order__status__in=[
                PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED])
        .values("material__category__name")
        .annotate(value=Coalesce(Sum(F("quantity") * F("unit_price"), output_field=_DEC),
                                 Value(_ZERO), output_field=_DEC))
        .order_by("-value")
    )
    return [{"category": r["material__category__name"] or "Uncategorised", "value": r["value"]}
            for r in qs]


def supplier_performance():
    """Per-supplier scorecard: spend, orders, rating and dispute count."""
    rows = []
    for v in Vendor.objects.all():
        agg = v.purchase_orders.exclude(
            status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED]
        ).aggregate(total=Coalesce(Sum("total"), Value(_ZERO), output_field=_DEC),
                    orders=Count("id"))
        disputes = v.bills.filter(status=VendorBill.Status.DISPUTED).count()
        if agg["orders"]:
            rows.append({
                "vendor": v.name, "rating": v.rating, "orders": agg["orders"],
                "total": agg["total"], "disputes": disputes,
            })
    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


def pending_counts():
    """Cross-document pending queue counts for the dashboard KPIs."""
    return {
        "rfqs": RequestForQuotation.objects.filter(
            status=RequestForQuotation.Status.SENT).count(),
        "pos_draft": PurchaseOrder.objects.filter(
            status=PurchaseOrder.Status.DRAFT).count(),
        "approvals": ApprovalRequest.objects.filter(
            status=ApprovalRequest.Status.PENDING).count(),
        "grns": GoodsReceiptNote.objects.filter(
            status=GoodsReceiptNote.Status.DRAFT).count(),
        "invoices": VendorBill.objects.filter(
            status__in=[VendorBill.Status.DRAFT, VendorBill.Status.MATCHED]).count(),
        "payments": Payment.objects.filter(
            status=Payment.Status.PENDING).count(),
    }
