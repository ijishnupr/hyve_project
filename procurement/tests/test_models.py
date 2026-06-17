"""Unit tests for model behaviour: numbering and computed totals."""
from decimal import Decimal

import pytest

from procurement.models import (
    DocumentCounter,
    PurchaseOrder,
    PurchaseOrderLine,
)

pytestmark = pytest.mark.django_db


def test_document_counter_is_sequential():
    a = DocumentCounter.next_number("PO")
    b = DocumentCounter.next_number("PO")
    assert a.endswith("00001")
    assert b.endswith("00002")
    assert a.startswith("PO-")


def test_po_auto_numbering(project, vendor, manager):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    assert po.number.startswith("PO-")


def test_po_recalculate_totals(project, vendor, material, manager):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po,
        material=material,
        quantity=Decimal("100"),
        unit_price=Decimal("400"),
        tax_rate=Decimal("18"),
    )
    po.recalculate_totals()
    po.refresh_from_db()
    assert po.subtotal == Decimal("40000.00")
    assert po.tax_amount == Decimal("7200.00")
    assert po.total == Decimal("47200.00")
