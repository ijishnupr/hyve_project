"""Tests for the audit trail, notifications and contract-expiry alerts."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    AuditLog,
    Notification,
    PurchaseContract,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
)
from procurement.tasks import send_contract_expiry_alerts

pytestmark = pytest.mark.django_db


def test_issue_po_writes_audit_and_notification(project, vendor, material, manager):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("10"),
        unit_price=Decimal("100"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)

    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(PurchaseOrder)
    assert AuditLog.objects.filter(content_type=ct, object_id=po.id, to_status="ISSUED").exists()
    assert Notification.objects.filter(kind=Notification.Kind.PO).exists()


def test_requisition_submit_notifies_managers(project, material, manager):
    pr = PurchaseRequisition.objects.create(project=project, requested_by=manager)
    PurchaseRequisitionLine.objects.create(requisition=pr, material=material, quantity=Decimal("5"))
    services.submit_requisition(pr)
    note = Notification.objects.filter(kind=Notification.Kind.APPROVAL).first()
    assert note is not None
    assert note.recipient_role == "PROCUREMENT_MANAGER"


def test_notifications_for_role_filtering(manager, accountant):
    Notification.objects.create(kind="PAYMENT", message="acc only",
                                recipient_role="ACCOUNTANT")
    Notification.objects.create(kind="GENERAL", message="broadcast")
    mgr_notes = services.notifications_for(manager)
    acc_notes = services.notifications_for(accountant)
    assert any(n.message == "broadcast" for n in mgr_notes)
    assert any(n.message == "acc only" for n in acc_notes)
    assert not any(n.message == "acc only" for n in mgr_notes)


def test_contract_expiry_alert(vendor, manager):
    PurchaseContract.objects.create(
        title="Expiring soon", vendor=vendor, created_by=manager,
        status=PurchaseContract.Status.ACTIVE,
        start_date=date(2026, 1, 1), end_date=date.today() + timedelta(days=10))
    created = send_contract_expiry_alerts(days=30)
    assert created == 1
    assert Notification.objects.filter(kind=Notification.Kind.CONTRACT).count() == 1
    # Idempotent — does not duplicate the alert.
    assert send_contract_expiry_alerts(days=30) == 0


def test_notification_api(api, manager):
    Notification.objects.create(kind="GENERAL", message="hello", recipient=manager)
    resp = api.get("/api/notifications/")
    assert resp.status_code == 200
    assert resp.data["count"] >= 1
