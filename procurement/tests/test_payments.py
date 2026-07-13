"""Tests for supplier payments (advance, partial, settle bill)."""
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    GoodsReceiptNote,
    GRNLine,
    Payment,
    PurchaseOrder,
    PurchaseOrderLine,
    VendorBill,
    VendorBillLine,
)

pytestmark = pytest.mark.django_db


def _approved_bill(project, vendor, material, manager, accountant):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("100"),
        unit_price=Decimal("400"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("100"), accepted_quantity=Decimal("100"))
    services.confirm_grn(grn)
    bill = VendorBill.objects.create(vendor=vendor, purchase_order=po,
                                     vendor_invoice_number="INV-PAY", created_by=accountant)
    VendorBillLine.objects.create(bill=bill, po_line=po.lines.first(),
                                  quantity=Decimal("100"), unit_price=Decimal("400"), tax_rate=Decimal("18"))
    bill.recalculate_totals()
    services.run_three_way_match(bill)
    services.approve_bill(bill)
    return bill


def test_partial_payments_settle_bill(project, vendor, material, manager, accountant):
    bill = _approved_bill(project, vendor, material, manager, accountant)
    assert bill.total == Decimal("47200.00")

    p1 = Payment.objects.create(vendor=vendor, bill=bill, amount=Decimal("20000.00"),
                                payment_type="AGAINST_BILL", created_by=accountant)
    services.post_payment(p1)
    bill.refresh_from_db()
    assert bill.status == VendorBill.Status.APPROVED  # still outstanding
    assert bill.outstanding == Decimal("27200.00")

    p2 = Payment.objects.create(vendor=vendor, bill=bill, amount=Decimal("27200.00"),
                                payment_type="AGAINST_BILL", created_by=accountant)
    services.post_payment(p2)
    bill.refresh_from_db()
    assert bill.status == VendorBill.Status.PAID
    assert bill.outstanding == Decimal("0.00")


def test_cancel_payment_reverts_paid_bill(project, vendor, material, manager, accountant):
    bill = _approved_bill(project, vendor, material, manager, accountant)
    p = Payment.objects.create(vendor=vendor, bill=bill, amount=bill.total,
                               payment_type="AGAINST_BILL", created_by=accountant)
    services.post_payment(p)
    bill.refresh_from_db()
    assert bill.status == VendorBill.Status.PAID
    services.cancel_payment(p)
    bill.refresh_from_db()
    assert bill.status == VendorBill.Status.APPROVED


def test_advance_payment_no_bill(vendor, accountant):
    p = Payment.objects.create(vendor=vendor, amount=Decimal("5000.00"),
                               payment_type="ADVANCE", created_by=accountant)
    services.post_payment(p)
    p.refresh_from_db()
    assert p.status == Payment.Status.PAID


def test_payment_api(project, vendor, material, manager, accountant):
    from rest_framework.test import APIClient
    bill = _approved_bill(project, vendor, material, manager, accountant)
    acc = APIClient(); acc.force_authenticate(user=accountant)
    resp = acc.post("/api/payments/", {
        "vendor": vendor.id, "bill": bill.id, "amount": "47200.00",
        "payment_type": "AGAINST_BILL", "method": "BANK_TRANSFER"}, format="json")
    assert resp.status_code == 201, resp.content
    pid = resp.data["id"]
    posted = acc.post(f"/api/payments/{pid}/post_payment/")
    assert posted.status_code == 200
    assert posted.data["status"] == "PAID"
