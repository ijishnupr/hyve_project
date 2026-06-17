"""User model with role-based access for the procurement domain."""
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    """Coarse-grained roles that drive procurement permissions."""

    ADMIN = "ADMIN", "Administrator"
    PROCUREMENT_MANAGER = "PROCUREMENT_MANAGER", "Procurement Manager"
    SITE_ENGINEER = "SITE_ENGINEER", "Site Engineer"
    ACCOUNTANT = "ACCOUNTANT", "Accountant"
    VIEWER = "VIEWER", "Viewer"


class User(AbstractUser):
    """Custom user; email is required and used as the contact identity."""

    email = models.EmailField("email address", unique=True)
    role = models.CharField(
        max_length=32, choices=Role.choices, default=Role.VIEWER
    )
    phone = models.CharField(max_length=20, blank=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    # Convenience predicates used by permission classes.
    @property
    def can_manage_procurement(self) -> bool:
        return self.role in {Role.ADMIN, Role.PROCUREMENT_MANAGER}

    @property
    def can_approve(self) -> bool:
        return self.role in {Role.ADMIN, Role.PROCUREMENT_MANAGER}

    @property
    def can_manage_bills(self) -> bool:
        return self.role in {Role.ADMIN, Role.ACCOUNTANT}
