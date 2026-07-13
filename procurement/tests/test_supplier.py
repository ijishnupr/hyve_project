"""Tests for extended supplier management (contacts / addresses / banks / documents)."""
import pytest
from rest_framework.test import APIClient

from procurement.models import (
    SupplierAddress,
    SupplierBankAccount,
    SupplierContact,
)

pytestmark = pytest.mark.django_db


def test_add_supplier_contact_via_api(api, vendor):
    resp = api.post(
        "/api/supplier-contacts/",
        {"vendor": vendor.id, "name": "Ravi Kumar", "designation": "Sales",
         "email": "ravi@vendor.com", "is_primary": True},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert SupplierContact.objects.filter(vendor=vendor, name="Ravi Kumar").exists()


def test_vendor_detail_nests_children(api, vendor):
    SupplierContact.objects.create(vendor=vendor, name="A")
    SupplierAddress.objects.create(vendor=vendor, line1="1 MG Rd", city="Pune")
    SupplierBankAccount.objects.create(
        vendor=vendor, account_name="Test Vendor", account_number="123", bank_name="HDFC")

    resp = api.get(f"/api/vendors/{vendor.id}/")
    assert resp.status_code == 200
    assert len(resp.data["contacts"]) == 1
    assert len(resp.data["addresses"]) == 1
    assert len(resp.data["bank_accounts"]) == 1


def test_viewer_cannot_add_contact(viewer, vendor):
    client = APIClient()
    client.force_authenticate(user=viewer)
    resp = client.post(
        "/api/supplier-contacts/",
        {"vendor": vendor.id, "name": "X"}, format="json")
    assert resp.status_code == 403


def test_web_vendor_child_add_and_delete(client, manager, vendor):
    client.force_login(manager)
    add = client.post(
        f"/vendors/{vendor.id}/contact/add/",
        {"name": "Site Contact", "designation": "PM", "email": "", "phone": "999"},
    )
    assert add.status_code == 302
    contact = SupplierContact.objects.get(vendor=vendor, name="Site Contact")

    delete = client.get(f"/vendors/{vendor.id}/contact/{contact.id}/delete/")
    assert delete.status_code == 302
    assert not SupplierContact.objects.filter(pk=contact.id).exists()


def test_new_vendor_fields_persist(vendor):
    vendor.pan = "ABCDE1234F"
    vendor.credit_limit = "500000.00"
    vendor.save()
    vendor.refresh_from_db()
    assert vendor.pan == "ABCDE1234F"
    assert str(vendor.credit_limit) == "500000.00"
