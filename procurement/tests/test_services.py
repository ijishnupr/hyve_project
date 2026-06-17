"""Tests for the procurement state-machine services."""
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    GoodsReceiptNote,
    GRNLine,
    PurchaseOrder,
    PurchaseOrderLine,
    VendorBill,
    VendorBillLine,
)

pytestmark = pytest.mark.django_db


def _make_po(project, vendor, material, manager, *, qty="100", price="400"):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po,
        material=material,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        tax_rate=Decimal("18"),
    )
    return po


def test_issue_po_requires_draft(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.ISSUED
    assert po.total == Decimal("47200.00")
    with pytest.raises(services.TransitionError):
        services.issue_purchase_order(po, user=manager)


def test_grn_confirm_posts_received_quantity(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    po_line = po.lines.first()

    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(
        grn=grn,
        po_line=po_line,
        received_quantity=Decimal("60"),
        accepted_quantity=Decimal("60"),
    )
    services.confirm_grn(grn)

    po_line.refresh_from_db()
    po.refresh_from_db()
    assert po_line.received_quantity == Decimal("60.000")
    assert po.status == PurchaseOrder.Status.PARTIALLY_RECEIVED


def test_grn_cannot_over_receive(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    po_line = po.lines.first()

    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(
        grn=grn,
        po_line=po_line,
        received_quantity=Decimal("150"),
        accepted_quantity=Decimal("150"),
    )
    with pytest.raises(services.TransitionError):
        services.confirm_grn(grn)


def test_grn_cancel_reverses_quantity(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    po_line = po.lines.first()

    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(
        grn=grn, po_line=po_line, received_quantity=Decimal("100"), accepted_quantity=Decimal("100")
    )
    services.confirm_grn(grn)
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.RECEIVED

    services.cancel_grn(grn)
    po_line.refresh_from_db()
    po.refresh_from_db()
    assert po_line.received_quantity == Decimal("0.000")
    assert po.status == PurchaseOrder.Status.ISSUED


def test_three_way_match_success(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    po_line = po.lines.first()

    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(
        grn=grn, po_line=po_line, received_quantity=Decimal("100"), accepted_quantity=Decimal("100")
    )
    services.confirm_grn(grn)

    bill = VendorBill.objects.create(
        vendor=vendor,
        purchase_order=po,
        vendor_invoice_number="INV-1",
        created_by=manager,
    )
    VendorBillLine.objects.create(
        bill=bill, po_line=po_line, quantity=Decimal("100"), unit_price=Decimal("400"), tax_rate=Decimal("18")
    )
    services.run_three_way_match(bill)
    bill.refresh_from_db()
    assert bill.match_status == VendorBill.MatchStatus.MATCHED
    assert bill.status == VendorBill.Status.MATCHED


def test_three_way_match_price_exception(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    po_line = po.lines.first()

    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(
        grn=grn, po_line=po_line, received_quantity=Decimal("100"), accepted_quantity=Decimal("100")
    )
    services.confirm_grn(grn)

    bill = VendorBill.objects.create(
        vendor=vendor, purchase_order=po, vendor_invoice_number="INV-2", created_by=manager
    )
    VendorBillLine.objects.create(
        bill=bill, po_line=po_line, quantity=Decimal("100"), unit_price=Decimal("450"), tax_rate=Decimal("18")
    )
    services.run_three_way_match(bill)
    bill.refresh_from_db()
    assert bill.match_status == VendorBill.MatchStatus.EXCEPTION
    assert bill.status == VendorBill.Status.DISPUTED
