"""Tests for purchase contracts (blanket orders, pricing, renewal, consumption)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    ContractLine,
    PurchaseContract,
    PurchaseOrder,
    PurchaseOrderLine,
)

pytestmark = pytest.mark.django_db


def _contract(vendor, material, manager, *, total="1000000"):
    c = PurchaseContract.objects.create(
        title="Cement supply", vendor=vendor, created_by=manager,
        start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
        total_value=Decimal(total))
    ContractLine.objects.create(contract=c, material=material,
                                unit_price=Decimal("380"), tax_rate=Decimal("18"))
    return c


def test_activate_and_terminate(vendor, material, manager):
    c = _contract(vendor, material, manager)
    services.activate_contract(c)
    c.refresh_from_db()
    assert c.status == PurchaseContract.Status.ACTIVE
    services.terminate_contract(c)
    c.refresh_from_db()
    assert c.status == PurchaseContract.Status.TERMINATED


def test_renew_clones_lines(vendor, material, manager):
    c = _contract(vendor, material, manager)
    services.activate_contract(c)
    new = services.renew_contract(c, start_date=date(2027, 1, 1), end_date=date(2027, 12, 31), user=manager)
    c.refresh_from_db()
    assert c.status == PurchaseContract.Status.RENEWED
    assert new.status == PurchaseContract.Status.ACTIVE
    assert new.renewed_from_id == c.id
    assert new.lines.count() == 1


def test_po_issue_draws_down_contract(project, vendor, material, manager):
    c = _contract(vendor, material, manager)
    services.activate_contract(c)
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, contract=c, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("100"),
        unit_price=Decimal("380"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)
    c.refresh_from_db()
    assert c.consumed_value == po.total
    assert c.remaining_value == (Decimal("1000000.00") - po.total)


def test_contract_api_flow(api, vendor, material):
    resp = api.post("/api/purchase-contracts/", {
        "title": "Steel rate contract", "vendor": vendor.id, "contract_type": "RATE",
        "start_date": "2026-01-01", "end_date": "2026-12-31", "total_value": "500000.00",
        "lines": [{"material": material.id, "unit_price": "50", "tax_rate": "18"}]},
        format="json")
    assert resp.status_code == 201, resp.content
    cid = resp.data["id"]
    act = api.post(f"/api/purchase-contracts/{cid}/activate/")
    assert act.status_code == 200
    assert act.data["status"] == "ACTIVE"
