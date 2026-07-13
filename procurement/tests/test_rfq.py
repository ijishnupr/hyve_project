"""Tests for the RFQ flow and PR -> RFQ conversion."""
from decimal import Decimal

import pytest

from procurement import services
from procurement.models import (
    PurchaseRequisition,
    PurchaseRequisitionLine,
    RequestForQuotation,
)

pytestmark = pytest.mark.django_db


def _approved_pr(project, material, manager):
    pr = PurchaseRequisition.objects.create(project=project, requested_by=manager)
    PurchaseRequisitionLine.objects.create(requisition=pr, material=material, quantity=Decimal("50"))
    services.submit_requisition(pr)
    services.approve_requisition(pr, user=manager)
    return pr


def test_create_rfq_from_requisition_copies_lines(project, material, manager):
    pr = _approved_pr(project, material, manager)
    rfq = services.create_rfq_from_requisition(pr, user=manager)
    assert rfq.status == RequestForQuotation.Status.DRAFT
    assert rfq.lines.count() == 1
    assert rfq.requisition_id == pr.id


def test_rfq_from_unapproved_pr_rejected(project, material, manager):
    pr = PurchaseRequisition.objects.create(project=project, requested_by=manager)
    PurchaseRequisitionLine.objects.create(requisition=pr, material=material, quantity=Decimal("5"))
    with pytest.raises(services.TransitionError):
        services.create_rfq_from_requisition(pr, user=manager)


def test_send_rfq_requires_lines_and_vendors(project, material, manager, vendor):
    rfq = RequestForQuotation.objects.create(project=project, created_by=manager)
    with pytest.raises(services.TransitionError):
        services.send_rfq(rfq)  # no lines
    from procurement.models import RFQLine
    RFQLine.objects.create(rfq=rfq, material=material, quantity=Decimal("10"))
    with pytest.raises(services.TransitionError):
        services.send_rfq(rfq)  # no vendors
    rfq.vendors.add(vendor)
    services.send_rfq(rfq)
    rfq.refresh_from_db()
    assert rfq.status == RequestForQuotation.Status.SENT
    assert rfq.sent_at is not None


def test_rfq_api_create_and_send(api, project, material, vendor):
    resp = api.post(
        "/api/rfqs/",
        {"project": project.id, "vendors": [vendor.id],
         "lines": [{"material": material.id, "quantity": "20"}]},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    rfq_id = resp.data["id"]
    sent = api.post(f"/api/rfqs/{rfq_id}/send/")
    assert sent.status_code == 200
    assert sent.data["status"] == "SENT"


def test_close_only_sent_rfq(project, material, manager, vendor):
    rfq = RequestForQuotation.objects.create(project=project, created_by=manager)
    with pytest.raises(services.TransitionError):
        services.close_rfq(rfq)
