"""Shared pytest fixtures for procurement tests."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from procurement.models import Material, Project, UnitOfMeasure, Vendor

User = get_user_model()


@pytest.fixture
def manager(db):
    return User.objects.create_user(
        username="manager",
        email="manager@example.com",
        password="pass12345",
        role="PROCUREMENT_MANAGER",
    )


@pytest.fixture
def accountant(db):
    return User.objects.create_user(
        username="accountant",
        email="acc@example.com",
        password="pass12345",
        role="ACCOUNTANT",
    )


@pytest.fixture
def viewer(db):
    return User.objects.create_user(
        username="viewer",
        email="viewer@example.com",
        password="pass12345",
        role="VIEWER",
    )


@pytest.fixture
def api(manager):
    client = APIClient()
    client.force_authenticate(user=manager)
    return client


@pytest.fixture
def project(db):
    return Project.objects.create(code="PRJ-T1", name="Test Site", budget=Decimal("1000000"))


@pytest.fixture
def vendor(db):
    return Vendor.objects.create(code="VEN-T1", name="Test Vendor", email="v@example.com")


@pytest.fixture
def material(db):
    return Material.objects.create(
        code="MAT-T1", name="Cement", unit=UnitOfMeasure.BAG, default_tax_rate=Decimal("18")
    )
