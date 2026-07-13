"""Tests for PO revisions, email, reopen and PDF/attachments."""
from decimal import Decimal

import pytest
from django.core import mail

from procurement import services
from procurement.models import PurchaseOrder, PurchaseOrderLine

pytestmark = pytest.mark.django_db


def _make_po(project, vendor, material, manager):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("10"),
        unit_price=Decimal("100"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    return po


def test_issue_logs_a_revision(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    assert po.revisions.count() == 1
    assert po.revisions.first().revision == 0


def test_reopen_bumps_revision_and_reissue_logs_again(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    services.reopen_purchase_order(po, user=manager)
    po.refresh_from_db()
    assert po.status == PurchaseOrder.Status.DRAFT
    assert po.revision == 1
    services.issue_purchase_order(po, user=manager)
    assert po.revisions.count() == 2


def test_cannot_reopen_with_confirmed_receipt(project, vendor, material, manager):
    from procurement.models import GoodsReceiptNote, GRNLine
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("10"), accepted_quantity=Decimal("10"))
    services.confirm_grn(grn)
    with pytest.raises(services.TransitionError):
        services.reopen_purchase_order(po, user=manager)


def test_email_po_to_vendor(project, vendor, material, manager):
    po = _make_po(project, vendor, material, manager)
    services.issue_purchase_order(po, user=manager)
    services.email_purchase_order(po)
    po.refresh_from_db()
    assert po.emailed_at is not None
    assert len(mail.outbox) == 1
    assert po.number in mail.outbox[0].subject


def test_email_requires_vendor_email(project, material, manager):
    from procurement.models import Vendor
    v = Vendor.objects.create(code="NOEMAIL", name="No Email Co")
    po = _make_po(project, v, material, manager)
    services.issue_purchase_order(po, user=manager)
    with pytest.raises(services.TransitionError):
        services.email_purchase_order(po)


def test_po_pdf_renders(client, manager, project, vendor, material):
    client.force_login(manager)
    po = _make_po(project, vendor, material, manager)
    resp = client.get(f"/purchase-orders/{po.id}/pdf/")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


def test_attachment_upload_via_api(api, project, vendor, material, manager):
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.contrib.contenttypes.models import ContentType
    po = _make_po(project, vendor, material, manager)
    ct = ContentType.objects.get(app_label="procurement", model="purchaseorder")
    f = SimpleUploadedFile("po.txt", b"hello", content_type="text/plain")
    resp = api.post("/api/attachments/", {
        "content_type": ct.id, "object_id": po.id, "title": "Spec", "kind": "OTHER", "file": f,
    }, format="multipart")
    assert resp.status_code == 201, resp.content
    assert resp.data["title"] == "Spec"
