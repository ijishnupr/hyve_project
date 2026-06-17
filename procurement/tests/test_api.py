"""End-to-end API tests covering auth, permissions and the procurement flow."""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_requires_authentication():
    client = APIClient()
    resp = client.get("/api/vendors/")
    assert resp.status_code == 401


def test_viewer_cannot_create_vendor(viewer):
    client = APIClient()
    client.force_authenticate(user=viewer)
    resp = client.post("/api/vendors/", {"code": "X", "name": "Y"}, format="json")
    assert resp.status_code == 403


def test_manager_creates_vendor(api):
    resp = api.post("/api/vendors/", {"code": "VEN-9", "name": "Acme"}, format="json")
    assert resp.status_code == 201, resp.content
    assert resp.data["code"] == "VEN-9"


def test_full_procurement_flow(api, project, vendor, material, manager, accountant):
    # 1. Create + submit + approve a requisition.
    pr_resp = api.post(
        "/api/requisitions/",
        {
            "project": project.id,
            "lines": [{"material": material.id, "quantity": "100"}],
        },
        format="json",
    )
    assert pr_resp.status_code == 201, pr_resp.content
    pr_id = pr_resp.data["id"]
    assert api.post(f"/api/requisitions/{pr_id}/submit/").status_code == 200
    assert api.post(f"/api/requisitions/{pr_id}/approve/").status_code == 200

    # 2. Create + issue a PO.
    po_resp = api.post(
        "/api/purchase-orders/",
        {
            "vendor": vendor.id,
            "project": project.id,
            "requisition": pr_id,
            "lines": [
                {"material": material.id, "quantity": "100", "unit_price": "400", "tax_rate": "18"}
            ],
        },
        format="json",
    )
    assert po_resp.status_code == 201, po_resp.content
    po_id = po_resp.data["id"]
    assert po_resp.data["total"] == "47200.00"
    po_line_id = po_resp.data["lines"][0]["id"]

    issue = api.post(f"/api/purchase-orders/{po_id}/issue/")
    assert issue.status_code == 200
    assert issue.data["status"] == "ISSUED"

    # 3. Receive goods via a GRN.
    grn_resp = api.post(
        "/api/grns/",
        {
            "purchase_order": po_id,
            "lines": [
                {"po_line": po_line_id, "received_quantity": "100", "accepted_quantity": "100"}
            ],
        },
        format="json",
    )
    assert grn_resp.status_code == 201, grn_resp.content
    grn_id = grn_resp.data["id"]
    confirm = api.post(f"/api/grns/{grn_id}/confirm/")
    assert confirm.status_code == 200
    assert confirm.data["status"] == "CONFIRMED"

    # 4. Create a vendor bill and run 3-way match (an accountant handles billing).
    acc = APIClient()
    acc.force_authenticate(user=accountant)
    bill_resp = acc.post(
        "/api/bills/",
        {
            "vendor": vendor.id,
            "purchase_order": po_id,
            "vendor_invoice_number": "SUPP-INV-1",
            "lines": [
                {"po_line": po_line_id, "quantity": "100", "unit_price": "400", "tax_rate": "18"}
            ],
        },
        format="json",
    )
    assert bill_resp.status_code == 201, bill_resp.content
    bill_id = bill_resp.data["id"]
    match = acc.post(f"/api/bills/{bill_id}/match/")
    assert match.status_code == 200
    assert match.data["match_status"] == "MATCHED"

    approve = acc.post(f"/api/bills/{bill_id}/approve/")
    assert approve.status_code == 200
    paid = acc.post(f"/api/bills/{bill_id}/mark-paid/")
    assert paid.status_code == 200
    assert paid.data["status"] == "PAID"


def test_cannot_submit_empty_requisition(api, project):
    # Serializer rejects requisitions without lines at creation time.
    resp = api.post(
        "/api/requisitions/",
        {"project": project.id, "lines": []},
        format="json",
    )
    assert resp.status_code == 400
