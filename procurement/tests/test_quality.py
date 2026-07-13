"""Tests for quality inspection (checklist -> pass/fail)."""
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    GoodsReceiptNote,
    GRNLine,
    PurchaseOrder,
    PurchaseOrderLine,
    QCChecklistItem,
    QualityInspection,
)

pytestmark = pytest.mark.django_db


def _confirmed_grn(project, vendor, material, manager):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("50"),
        unit_price=Decimal("100"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("50"), accepted_quantity=Decimal("50"))
    services.confirm_grn(grn)
    return grn


def test_inspection_passes_when_all_pass(project, vendor, material, manager):
    grn = _confirmed_grn(project, vendor, material, manager)
    insp = QualityInspection.objects.create(grn=grn)
    QCChecklistItem.objects.create(inspection=insp, description="Qty", result="PASS")
    QCChecklistItem.objects.create(inspection=insp, description="Spec", result="NA")
    services.submit_inspection(insp, user=manager)
    insp.refresh_from_db()
    assert insp.status == QualityInspection.Status.PASSED
    assert insp.inspected_by == manager


def test_inspection_fails_on_any_fail(project, vendor, material, manager):
    grn = _confirmed_grn(project, vendor, material, manager)
    insp = QualityInspection.objects.create(grn=grn)
    QCChecklistItem.objects.create(inspection=insp, description="Qty", result="PASS")
    QCChecklistItem.objects.create(inspection=insp, description="Damage", result="FAIL")
    services.submit_inspection(insp, user=manager)
    insp.refresh_from_db()
    assert insp.status == QualityInspection.Status.FAILED


def test_cannot_submit_with_pending_items(project, vendor, material, manager):
    grn = _confirmed_grn(project, vendor, material, manager)
    insp = QualityInspection.objects.create(grn=grn)
    QCChecklistItem.objects.create(inspection=insp, description="Qty")  # PENDING
    with pytest.raises(services.TransitionError):
        services.submit_inspection(insp, user=manager)


def test_inspection_api_flow(api, project, vendor, material, manager):
    grn = _confirmed_grn(project, vendor, material, manager)
    resp = api.post("/api/quality-inspections/", {
        "grn": grn.id,
        "items": [{"description": "Qty", "result": "PASS"},
                  {"description": "Spec", "result": "PASS"}],
    }, format="json")
    assert resp.status_code == 201, resp.content
    iid = resp.data["id"]
    sub = api.post(f"/api/quality-inspections/{iid}/submit/")
    assert sub.status_code == 200
    assert sub.data["status"] == "PASSED"
