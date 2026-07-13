"""Tests for purchase returns (reverse received qty + stock)."""
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    GoodsReceiptNote,
    GRNLine,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReturn,
    PurchaseReturnLine,
    StockItem,
    StockLedgerEntry,
)

pytestmark = pytest.mark.django_db


def _received_po(project, vendor, material, manager, qty="100"):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal(qty),
        unit_price=Decimal("400"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal(qty), accepted_quantity=Decimal(qty))
    services.confirm_grn(grn)
    return po


def test_confirm_return_reverses_stock_and_qty(project, vendor, material, manager):
    po = _received_po(project, vendor, material, manager)
    ret = PurchaseReturn.objects.create(purchase_order=po, vendor=vendor, created_by=manager,
                                        resolution="CREDIT_NOTE")
    PurchaseReturnLine.objects.create(purchase_return=ret, po_line=po.lines.first(),
                                      quantity=Decimal("30"))
    services.confirm_return(ret)

    line = po.lines.first(); line.refresh_from_db()
    assert line.received_quantity == Decimal("70.000")
    item = StockItem.objects.get(material=material, project=project)
    assert item.quantity_on_hand == Decimal("70.000")
    assert StockLedgerEntry.objects.filter(movement=StockLedgerEntry.Movement.RETURN).count() == 1
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.PARTIALLY_RECEIVED


def test_cannot_return_more_than_received(project, vendor, material, manager):
    po = _received_po(project, vendor, material, manager)
    ret = PurchaseReturn.objects.create(purchase_order=po, vendor=vendor, created_by=manager)
    PurchaseReturnLine.objects.create(purchase_return=ret, po_line=po.lines.first(),
                                      quantity=Decimal("150"))
    with pytest.raises(services.TransitionError):
        services.confirm_return(ret)


def test_cancel_confirmed_return_restores(project, vendor, material, manager):
    po = _received_po(project, vendor, material, manager)
    ret = PurchaseReturn.objects.create(purchase_order=po, vendor=vendor, created_by=manager)
    PurchaseReturnLine.objects.create(purchase_return=ret, po_line=po.lines.first(),
                                      quantity=Decimal("40"))
    services.confirm_return(ret)
    services.cancel_return(ret)
    line = po.lines.first(); line.refresh_from_db()
    assert line.received_quantity == Decimal("100.000")
    item = StockItem.objects.get(material=material, project=project)
    assert item.quantity_on_hand == Decimal("100.000")


def test_return_api_flow(api, project, vendor, material, manager):
    po = _received_po(project, vendor, material, manager)
    resp = api.post("/api/purchase-returns/", {
        "purchase_order": po.id, "vendor": vendor.id, "resolution": "REFUND",
        "lines": [{"po_line": po.lines.first().id, "quantity": "10"}]}, format="json")
    assert resp.status_code == 201, resp.content
    rid = resp.data["id"]
    conf = api.post(f"/api/purchase-returns/{rid}/confirm/")
    assert conf.status_code == 200
    assert conf.data["status"] == "CONFIRMED"
