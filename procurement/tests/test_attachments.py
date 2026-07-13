"""Tests for generic attachments across documents."""
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from procurement import services
from procurement.models import (
    Attachment,
    GoodsReceiptNote,
    GRNLine,
    PurchaseOrder,
    PurchaseOrderLine,
)

pytestmark = pytest.mark.django_db


def _grn(project, vendor, material, manager):
    po = PurchaseOrder.objects.create(project=project, vendor=vendor, created_by=manager)
    PurchaseOrderLine.objects.create(
        purchase_order=po, material=material, quantity=Decimal("10"),
        unit_price=Decimal("100"), tax_rate=Decimal("18"))
    po.recalculate_totals()
    services.issue_purchase_order(po, user=manager)
    grn = GoodsReceiptNote.objects.create(purchase_order=po, received_by=manager)
    GRNLine.objects.create(grn=grn, po_line=po.lines.first(),
                           received_quantity=Decimal("10"), accepted_quantity=Decimal("10"))
    services.confirm_grn(grn)
    return grn


def test_web_attachment_add_and_delete_on_grn(client, manager, project, vendor, material):
    grn = _grn(project, vendor, material, manager)
    client.force_login(manager)
    f = SimpleUploadedFile("challan.txt", b"delivery note", content_type="text/plain")
    resp = client.post(f"/attachments/goodsreceiptnote/{grn.id}/add/",
                       {"title": "Challan", "kind": "DELIVERY_NOTE", "file": f})
    assert resp.status_code == 302
    ct = ContentType.objects.get(app_label="procurement", model="goodsreceiptnote")
    att = Attachment.objects.get(content_type=ct, object_id=grn.id)
    assert att.title == "Challan"

    resp2 = client.get(f"/attachments/{att.id}/delete/")
    assert resp2.status_code == 302
    assert not Attachment.objects.filter(pk=att.id).exists()


def test_viewer_cannot_attach(client, viewer, project, vendor, material, manager):
    grn = _grn(project, vendor, material, manager)
    client.force_login(viewer)
    f = SimpleUploadedFile("x.txt", b"x", content_type="text/plain")
    resp = client.post(f"/attachments/goodsreceiptnote/{grn.id}/add/",
                       {"title": "X", "kind": "OTHER", "file": f})
    assert resp.status_code == 302  # redirected with error message
    assert Attachment.objects.count() == 0
