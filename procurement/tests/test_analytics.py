"""Tests for analytics aggregations + dashboard/analytics pages."""
from decimal import Decimal

import pytest

from procurement import analytics, services
from procurement.models import PurchaseOrder, PurchaseOrderLine

pytestmark = pytest.mark.django_db


def _issued_po(project, vendor, material, manager):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("100"),
        unit_price=Decimal("400"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)
    return po


def test_top_suppliers_and_monthly(project, vendor, material, manager):
    _issued_po(project, vendor, material, manager)
    top = analytics.top_suppliers()
    assert top and top[0]["vendor"] == vendor.name
    monthly = analytics.monthly_spend(6)
    assert sum(r["total"] for r in monthly) == Decimal("47200.00")


def test_pending_counts_keys():
    counts = analytics.pending_counts()
    assert set(counts) == {"rfqs", "pos_draft", "approvals", "grns", "invoices", "payments"}


def test_category_and_performance(project, vendor, material, manager):
    _issued_po(project, vendor, material, manager)
    cats = analytics.category_spend()
    assert cats  # at least one row
    perf = analytics.supplier_performance()
    assert perf[0]["vendor"] == vendor.name


def test_dashboard_and_analytics_pages_render(client, manager):
    client.force_login(manager)
    assert client.get("/").status_code == 200
    assert client.get("/analytics/").status_code == 200
