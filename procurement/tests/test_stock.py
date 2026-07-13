"""Tests for Stock Ledger integration from GRNs."""
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    GoodsReceiptNote,
    GRNLine,
    PurchaseOrder,
    PurchaseOrderLine,
    StockItem,
    StockLedgerEntry,
)

pytestmark = pytest.mark.django_db


def _issued_po(project, vendor, material, manager):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("100"),
        unit_price=Decimal("400"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)
    return po


def test_confirm_grn_posts_stock(project, vendor, material, manager):
    po = _issued_po(project, vendor, material, manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("60"), accepted_quantity=Decimal("55"),
                           rejected_quantity=Decimal("5"))
    services.confirm_grn(grn)

    item = StockItem.objects.get(material=material, project=project)
    assert item.quantity_on_hand == Decimal("55.000")  # only accepted qty enters stock
    entry = StockLedgerEntry.objects.get(material=material, project=project)
    assert entry.movement == StockLedgerEntry.Movement.RECEIPT
    assert entry.quantity == Decimal("55.000")
    assert entry.balance_after == Decimal("55.000")


def test_cancel_grn_reverses_stock(project, vendor, material, manager):
    po = _issued_po(project, vendor, material, manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("40"), accepted_quantity=Decimal("40"))
    services.confirm_grn(grn)
    services.cancel_grn(grn)

    item = StockItem.objects.get(material=material, project=project)
    assert item.quantity_on_hand == Decimal("0.000")
    assert StockLedgerEntry.objects.filter(
        movement=StockLedgerEntry.Movement.ADJUSTMENT).count() == 1


def test_back_order_quantity_tracked(project, vendor, material, manager):
    po = _issued_po(project, vendor, material, manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("30"), accepted_quantity=Decimal("30"))
    services.confirm_grn(grn)
    line = po.lines.first()
    line.refresh_from_db()
    assert line.pending_quantity == Decimal("70.000")  # outstanding back-order
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.PARTIALLY_RECEIVED


def test_stock_api_readonly(api, project, vendor, material, manager):
    po = _issued_po(project, vendor, material, manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("10"), accepted_quantity=Decimal("10"))
    services.confirm_grn(grn)
    resp = api.get("/api/stock-items/")
    assert resp.status_code == 200
    resp2 = api.get("/api/stock-ledger/")
    assert resp2.status_code == 200
    assert resp2.data["count"] >= 1
