"""Populate the database with representative construction procurement data.

Usage:  python manage.py seed_demo_data
Idempotent-ish: safe to run on an empty database; uses get_or_create for masters.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from procurement.models import (
    Material,
    MaterialCategory,
    Project,
    UnitOfMeasure,
    Vendor,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seed demo master data (projects, vendors, materials) and an admin user."

    @transaction.atomic
    def handle(self, *args, **options):
        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@example.com",
                "is_staff": True,
                "is_superuser": True,
                "role": "ADMIN",
            },
        )
        if created:
            admin.set_password("admin12345")
            admin.save()
            self.stdout.write(self.style.SUCCESS("Created admin / admin12345"))

        proj, _ = Project.objects.get_or_create(
            code="PRJ-001",
            defaults={
                "name": "Riverside Towers",
                "location": "Pune",
                "budget": Decimal("250000000.00"),
                "manager": admin,
            },
        )

        cat_cement, _ = MaterialCategory.objects.get_or_create(name="Cement & Binders")
        cat_steel, _ = MaterialCategory.objects.get_or_create(name="Steel & Reinforcement")
        cat_agg, _ = MaterialCategory.objects.get_or_create(name="Aggregates")

        materials = [
            ("MAT-CEM-OPC53", "OPC 53 Grade Cement", cat_cement, UnitOfMeasure.BAG, "2523"),
            ("MAT-STL-TMT12", "TMT Steel Bar 12mm Fe500", cat_steel, UnitOfMeasure.TON, "7214"),
            ("MAT-AGG-20MM", "Coarse Aggregate 20mm", cat_agg, UnitOfMeasure.BRASS, "2517"),
            ("MAT-SND-RIVER", "River Sand", cat_agg, UnitOfMeasure.BRASS, "2505"),
        ]
        for code, name, cat, unit, hsn in materials:
            Material.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "category": cat,
                    "unit": unit,
                    "hsn_code": hsn,
                },
            )

        Vendor.objects.get_or_create(
            code="VEN-001",
            defaults={
                "name": "Ultra Build Supplies Pvt Ltd",
                "gstin": "27ABCDE1234F1Z5",
                "contact_person": "Ramesh Kumar",
                "email": "sales@ultrabuild.example",
                "phone": "9876543210",
                "payment_terms_days": 30,
            },
        )
        Vendor.objects.get_or_create(
            code="VEN-002",
            defaults={
                "name": "Steel Junction Traders",
                "gstin": "27FGHIJ5678K2Z9",
                "contact_person": "Sunita Rao",
                "email": "orders@steeljunction.example",
                "phone": "9123456780",
                "payment_terms_days": 45,
            },
        )

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
