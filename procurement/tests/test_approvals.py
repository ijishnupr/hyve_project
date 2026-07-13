"""Tests for the approval-matrix workflow and PO issue gating."""
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    ApprovalDocumentType,
    ApprovalRequest,
    ApprovalRule,
    PurchaseOrder,
    PurchaseOrderLine,
)

pytestmark = pytest.mark.django_db


def _make_po(project, vendor, material, manager, *, qty="100", price="400"):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal(qty),
        unit_price=Decimal(price), tax_rate=Decimal("18"))
    po.recalculate_totals()
    return po


def _two_level_matrix():
    ApprovalRule.objects.create(
        name="L1 engineer", document_type=ApprovalDocumentType.PURCHASE_ORDER,
        level=1, role_required="SITE_ENGINEER", min_amount=Decimal("0"))
    ApprovalRule.objects.create(
        name="L2 manager", document_type=ApprovalDocumentType.PURCHASE_ORDER,
        level=2, role_required="PROCUREMENT_MANAGER", min_amount=Decimal("0"))


def test_no_rules_means_no_approval_required(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)  # no rules -> issues directly
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.ISSUED


def test_multi_level_approval_flow(project, vendor, material, manager, site_engineer):
    _two_level_matrix()
    po = _make_po(project, vendor, material, manager)

    req = services.submit_po_for_approval(po, user=manager)
    assert req.steps.count() == 2
    assert req.current_level == 1

    # Cannot issue while pending.
    with pytest.raises(services.TransitionError):
        services.issue_purchase_order(po, user=manager)

    step1 = req.steps.get(level=1)
    # Wrong role cannot approve level 1.
    with pytest.raises(services.TransitionError):
        services.approve_step(step1, user=manager)
    services.approve_step(step1, user=site_engineer)
    req.refresh_from_db()
    assert req.current_level == 2
    assert req.status == ApprovalRequest.Status.PENDING

    step2 = req.steps.get(level=2)
    services.approve_step(step2, user=manager)
    req.refresh_from_db()
    assert req.status == ApprovalRequest.Status.APPROVED

    # Now it issues.
    services.issue_purchase_order(po, user=manager)
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.ISSUED


def test_reject_blocks_issue(project, vendor, material, manager, site_engineer):
    _two_level_matrix()
    po = _make_po(project, vendor, material, manager)
    req = services.submit_po_for_approval(po, user=manager)
    services.reject_step(req.steps.get(level=1), user=site_engineer, comments="too costly")
    req.refresh_from_db()
    assert req.status == ApprovalRequest.Status.REJECTED
    with pytest.raises(services.TransitionError):
        services.issue_purchase_order(po, user=manager)


def test_threshold_excludes_small_po(project, vendor, material, manager):
    # Rule only applies above 1,000,000 — a small PO is unaffected.
    ApprovalRule.objects.create(
        name="big only", document_type=ApprovalDocumentType.PURCHASE_ORDER,
        level=1, role_required="PROCUREMENT_MANAGER", min_amount=Decimal("1000000"))
    po = _make_po(project, vendor, material, manager)  # total 47,200
    assert services.po_approval_rules_apply(po) is False
    services.issue_purchase_order(po, user=manager)
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.ISSUED


def test_admin_can_approve_any_level(project, vendor, material, manager, admin_user):
    _two_level_matrix()
    po = _make_po(project, vendor, material, manager)
    req = services.submit_po_for_approval(po, user=manager)
    services.approve_step(req.steps.get(level=1), user=admin_user)
    services.approve_step(req.steps.get(level=2), user=admin_user)
    req.refresh_from_db()
    assert req.status == ApprovalRequest.Status.APPROVED
