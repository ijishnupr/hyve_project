"""Read-only reporting queries for the procurement module.

Each function returns a list of plain dicts so the same logic backs both the
web report pages and the JSON report API, and is unit-testable in isolation.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce

from .models import (
    Payment,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)

_ZERO = Decimal("0.00")
_DEC = DecimalField(max_digits=18, decimal_places=2)


def purchase_register():
    """Every issued/closed PO — the core purchase register."""
    qs = (
        PurchaseOrder.objects.exclude(
            status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED])
        .select_related("vendor", "project")
        .order_by("-order_date")
    )
    return [{
        "number": po.number, "date": po.order_date, "vendor": po.vendor.name,
        "project": po.project.name, "status": po.get_status_display(), "total": po.total,
    } for po in qs]


def supplier_ledger(vendor: Vendor):
    """Running ledger of bills (debit) and payments (credit) for a supplier."""
    rows = []
    for b in VendorBill.objects.filter(vendor=vendor).exclude(
            status=VendorBill.Status.CANCELLED):
        rows.append({"date": b.bill_date, "ref": b.number, "particulars": "Bill",
                     "debit": b.total, "credit": _ZERO})
    for p in Payment.objects.filter(vendor=vendor, status=Payment.Status.PAID):
        rows.append({"date": p.payment_date, "ref": p.number, "particulars": "Payment",
                     "debit": _ZERO, "credit": p.amount})
    rows.sort(key=lambda r: (r["date"], r["ref"]))
    balance = _ZERO
    for r in rows:
        balance += r["debit"] - r["credit"]
        r["balance"] = balance
    return rows


def outstanding_pos():
    """POs still awaiting delivery, with their pending (undelivered) value."""
    result = []
    qs = (
        PurchaseOrder.objects.filter(
            status__in=[PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.PARTIALLY_RECEIVED])
        .select_related("vendor").prefetch_related("lines")
    )
    for po in qs:
        pending_value = sum(
            (ln.pending_quantity * ln.unit_price for ln in po.lines.all()
             if ln.pending_quantity > 0), _ZERO)
        result.append({
            "number": po.number, "vendor": po.vendor.name, "status": po.get_status_display(),
            "total": po.total, "pending_value": Decimal(pending_value).quantize(_ZERO),
        })
    return result


def pending_receipts():
    """PO lines with quantity still to be received (back orders)."""
    rows = []
    qs = (
        PurchaseOrderLine.objects.filter(
            purchase_order__status__in=[
                PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.PARTIALLY_RECEIVED])
        .select_related("purchase_order__vendor", "material")
    )
    for ln in qs:
        if ln.pending_quantity > 0:
            rows.append({
                "po": ln.purchase_order.number, "vendor": ln.purchase_order.vendor.name,
                "material": ln.material.name, "ordered": ln.quantity,
                "received": ln.received_quantity, "pending": ln.pending_quantity,
            })
    return rows


def pending_invoices():
    """POs with received goods that are not yet fully billed."""
    rows = []
    qs = (
        PurchaseOrder.objects.exclude(
            status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED])
        .select_related("vendor").prefetch_related("lines")
    )
    for po in qs:
        received = sum((ln.received_quantity for ln in po.lines.all()), Decimal("0"))
        billed = (
            VendorBillLine.objects.filter(
                bill__purchase_order=po)
            .exclude(bill__status=VendorBill.Status.CANCELLED)
            .aggregate(s=Coalesce(Sum("quantity"), Value(Decimal("0")),
                                  output_field=DecimalField()))["s"]
        )
        if received > billed:
            rows.append({
                "po": po.number, "vendor": po.vendor.name,
                "received_qty": received, "billed_qty": billed,
                "uninvoiced_qty": received - billed,
            })
    return rows


def purchase_by_supplier():
    qs = (
        PurchaseOrder.objects.exclude(
            status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED])
        .values("vendor__name")
        .annotate(total=Coalesce(Sum("total"), Value(_ZERO), output_field=_DEC),
                  orders=Sum(Value(1)))
        .order_by("-total")
    )
    return [{"vendor": r["vendor__name"], "orders": r["orders"], "total": r["total"]} for r in qs]


def purchase_by_item():
    qs = (
        PurchaseOrderLine.objects.exclude(
            purchase_order__status__in=[
                PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED])
        .values("material__name")
        .annotate(
            qty=Coalesce(Sum("quantity"), Value(Decimal("0")), output_field=DecimalField()),
            value=Coalesce(Sum(F("quantity") * F("unit_price"), output_field=_DEC),
                           Value(_ZERO), output_field=_DEC))
        .order_by("-value")
    )
    return [{"material": r["material__name"], "qty": r["qty"], "value": r["value"]} for r in qs]


def price_variance():
    """Billed unit prices that differ from the ordered PO price."""
    rows = []
    qs = (
        VendorBillLine.objects.exclude(bill__status=VendorBill.Status.CANCELLED)
        .select_related("po_line__material", "bill__vendor")
    )
    for bl in qs:
        po_price = bl.po_line.unit_price
        if bl.unit_price != po_price:
            rows.append({
                "bill": bl.bill.number, "vendor": bl.bill.vendor.name,
                "material": bl.po_line.material.name, "po_price": po_price,
                "billed_price": bl.unit_price, "variance": bl.unit_price - po_price,
            })
    return rows


# Registry mapping report slug -> (title, callable, column spec).
REPORTS = {
    "purchase-register": ("Purchase Register", purchase_register,
                          ["number", "date", "vendor", "project", "status", "total"]),
    "outstanding-pos": ("Outstanding Purchase Orders", outstanding_pos,
                        ["number", "vendor", "status", "total", "pending_value"]),
    "pending-receipts": ("Pending Receipts", pending_receipts,
                         ["po", "vendor", "material", "ordered", "received", "pending"]),
    "pending-invoices": ("Pending Invoices", pending_invoices,
                         ["po", "vendor", "received_qty", "billed_qty", "uninvoiced_qty"]),
    "purchase-by-supplier": ("Purchase by Supplier", purchase_by_supplier,
                             ["vendor", "orders", "total"]),
    "purchase-by-item": ("Purchase by Item", purchase_by_item,
                         ["material", "qty", "value"]),
    "price-variance": ("Price Variance", price_variance,
                       ["bill", "vendor", "material", "po_price", "billed_price", "variance"]),
}
