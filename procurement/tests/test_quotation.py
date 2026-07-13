"""Tests for supplier quotations and selection -> PO creation."""
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    PurchaseOrder,
    RequestForQuotation,
    RFQLine,
    SupplierQuotation,
    SupplierQuotationLine,
)

pytestmark = pytest.mark.django_db


def _sent_rfq(project, material, manager, vendor):
    rfq = RequestForQuotation.objects.create(project=project, created_by=manager)
    RFQLine.objects.create(rfq=rfq, material=material, quantity=Decimal("100"))
    rfq.vendors.add(vendor)
    services.send_rfq(rfq)
    return rfq


def _quote(rfq, vendor, manager, material, price):
    q = SupplierQuotation.objects.create(rfq=rfq, vendor=vendor, created_by=manager)
    SupplierQuotationLine.objects.create(
        quotation=q, material=material, quantity=Decimal("100"),
        unit_price=Decimal(price), tax_rate=Decimal("18"))
    q.recalculate_totals()
    return q


def test_select_quotation_creates_po_and_closes_rfq(project, material, manager, vendor):
    rfq = _sent_rfq(project, material, manager, vendor)
    q = _quote(rfq, vendor, manager, material, "400")
    po = services.select_quotation(q, user=manager)

    assert isinstance(po, PurchaseOrder)
    assert po.status == PurchaseOrder.Status.DRAFT
    assert po.total == Decimal("47200.00")
    assert po.lines.count() == 1
    q.refresh_from_db(); rfq.refresh_from_db()
    assert q.status == SupplierQuotation.Status.SELECTED
    assert q.purchase_order_id == po.id
    assert rfq.status == RequestForQuotation.Status.CLOSED


def test_selecting_one_rejects_the_others(project, material, manager, vendor):
    from procurement.models import Vendor
    v2 = Vendor.objects.create(code="VEN-Q2", name="Second Vendor")
    rfq = _sent_rfq(project, material, manager, vendor)
    rfq.vendors.add(v2)
    q1 = _quote(rfq, vendor, manager, material, "400")
    q2 = _quote(rfq, v2, manager, material, "420")
    services.select_quotation(q1, user=manager)
    q2.refresh_from_db()
    assert q2.status == SupplierQuotation.Status.REJECTED


def test_quotation_api_flow(api, project, material, vendor, manager):
    rfq = _sent_rfq(project, material, manager, vendor)
    resp = api.post(
        "/api/quotations/",
        {"rfq": rfq.id, "vendor": vendor.id, "delivery_days": 7,
         "lines": [{"material": material.id, "quantity": "100", "unit_price": "400", "tax_rate": "18"}]},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert resp.data["total"] == "47200.00"
    qid = resp.data["id"]
    sel = api.post(f"/api/quotations/{qid}/select/")
    assert sel.status_code == 200
    assert sel.data["status"] == "SELECTED"
    assert sel.data["purchase_order"] is not None


def test_cannot_select_already_selected(project, material, manager, vendor):
    rfq = _sent_rfq(project, material, manager, vendor)
    q = _quote(rfq, vendor, manager, material, "400")
    services.select_quotation(q, user=manager)
    with pytest.raises(services.TransitionError):
        services.select_quotation(q, user=manager)
