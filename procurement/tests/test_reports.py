"""Tests for procurement reports."""
from decimal import Decimal

import pytest

from procurement import reports, services
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


def _issued_po(project, vendor, material, manager, price="400"):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("100"),
        unit_price=Decimal(price), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)
    return po


def test_purchase_register_and_by_supplier(project, vendor, material, manager):
    _issued_po(project, vendor, material, manager)
    register = reports.purchase_register()
    assert len(register) == 1
    by_supplier = reports.purchase_by_supplier()
    assert by_supplier[0]["vendor"] == vendor.name
    assert by_supplier[0]["total"] == Decimal("47200.00")


def test_outstanding_and_pending_receipts(project, vendor, material, manager):
    _issued_po(project, vendor, material, manager)
    assert len(reports.outstanding_pos()) == 1
    pr = reports.pending_receipts()
    assert pr[0]["pending"] == Decimal("100.000")


def test_price_variance(project, vendor, material, manager, accountant):
    po = _issued_po(project, vendor, material, manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("100"), accepted_quantity=Decimal("100"))
    services.confirm_grn(grn)
    bill = VendorBill.objects.create(vendor=vendor, purchase_order=po,
                                     vendor_invoice_number="INV-V", created_by=accountant)
    VendorBillLine.objects.create(bill=bill, po_line=po.lines.first(),
                                  quantity=Decimal("100"), unit_price=Decimal("450"), tax_rate=Decimal("18"))
    bill.recalculate_totals()
    variance = reports.price_variance()
    assert variance[0]["variance"] == Decimal("50.00")


def test_report_api(api, project, vendor, material, manager):
    _issued_po(project, vendor, material, manager)
    resp = api.get("/api/reports/purchase-by-supplier/")
    assert resp.status_code == 200
    assert resp.data["report"] == "purchase-by-supplier"
    assert len(resp.data["rows"]) == 1
    assert api.get("/api/reports/does-not-exist/").status_code == 404


def test_supplier_ledger(project, vendor, material, manager, accountant):
    po = _issued_po(project, vendor, material, manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("100"), accepted_quantity=Decimal("100"))
    services.confirm_grn(grn)
    bill = VendorBill.objects.create(vendor=vendor, purchase_order=po,
                                     vendor_invoice_number="INV-L", created_by=accountant)
    VendorBillLine.objects.create(bill=bill, po_line=po.lines.first(),
                                  quantity=Decimal("100"), unit_price=Decimal("400"), tax_rate=Decimal("18"))
    bill.recalculate_totals()
    services.run_three_way_match(bill)
    services.approve_bill(bill)
    p = Payment.objects.create(vendor=vendor, bill=bill, amount=Decimal("20000.00"),
                               payment_type="AGAINST_BILL", created_by=accountant)
    services.post_payment(p)

    ledger = reports.supplier_ledger(vendor)
    # bill debit 47200, payment credit 20000 => balance 27200
    assert ledger[-1]["balance"] == Decimal("27200.00")
