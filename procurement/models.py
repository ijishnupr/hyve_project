"""
Domain models for construction procurement.

Flow:  Purchase Requisition  ->  Purchase Order  ->  Goods Receipt (GRN)
       ->  Vendor Bill (3-way matched against PO + GRN).

Master data: Project (site), Vendor, MaterialCategory, Material.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

TWO_PLACES = Decimal("0.01")
USER = settings.AUTH_USER_MODEL


class TimeStampedModel(models.Model):
    """Audit columns shared by every concrete model."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------------
class DocumentCounter(models.Model):
    """Per-prefix, per-year sequence used to generate human-readable numbers.

    Rows are locked with ``select_for_update`` to keep numbering gap-free and
    safe under concurrent requests.
    """

    prefix = models.CharField(max_length=12)
    year = models.PositiveIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("prefix", "year")

    def __str__(self) -> str:
        return f"{self.prefix}-{self.year}: {self.last_value}"

    @classmethod
    def next_number(cls, prefix: str) -> str:
        """Atomically allocate the next ``PREFIX-YYYY-00001`` style number."""
        from django.db import transaction

        year = timezone.now().year
        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(
                prefix=prefix, year=year
            )
            counter.last_value += 1
            counter.save(update_fields=["last_value"])
            return f"{prefix}-{year}-{counter.last_value:05d}"


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
class Project(TimeStampedModel):
    """A construction site / project that purchases are made against."""

    class Status(models.TextChoices):
        PLANNING = "PLANNING", "Planning"
        ACTIVE = "ACTIVE", "Active"
        ON_HOLD = "ON_HOLD", "On Hold"
        COMPLETED = "COMPLETED", "Completed"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    budget = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00")
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    manager = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects"
    )

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class Vendor(TimeStampedModel):
    """A supplier of materials or services."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    gstin = models.CharField("GSTIN", max_length=15, blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    payment_terms_days = models.PositiveIntegerField(
        default=30, help_text="Default net payment terms in days."
    )
    rating = models.PositiveSmallIntegerField(
        default=0, help_text="Performance rating 0-5."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class MaterialCategory(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "material categories"

    def __str__(self) -> str:
        return self.name


class UnitOfMeasure(models.TextChoices):
    """Common construction units."""

    NOS = "NOS", "Numbers"
    BAG = "BAG", "Bags"
    KG = "KG", "Kilograms"
    TON = "TON", "Metric Tonnes"
    CUM = "CUM", "Cubic Metres"
    SQM = "SQM", "Square Metres"
    RMT = "RMT", "Running Metres"
    LTR = "LTR", "Litres"
    QTL = "QTL", "Quintals"
    BRASS = "BRASS", "Brass"


class Material(TimeStampedModel):
    """A purchasable material / item (cement, steel, aggregates, ...)."""

    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(
        MaterialCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="materials",
    )
    unit = models.CharField(max_length=8, choices=UnitOfMeasure.choices)
    hsn_code = models.CharField("HSN code", max_length=10, blank=True)
    default_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("18.00")
    )
    specification = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


# ---------------------------------------------------------------------------
# Purchase Requisition
# ---------------------------------------------------------------------------
class PurchaseRequisition(TimeStampedModel):
    """An internal request raised from a site to procure materials."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CONVERTED = "CONVERTED", "Converted to PO"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=20, unique=True, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="requisitions"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    required_by = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    requested_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="requisitions"
    )
    approved_by = models.ForeignKey(
        USER,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_requisitions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("PR")
        super().save(*args, **kwargs)


class PurchaseRequisitionLine(models.Model):
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.CASCADE, related_name="lines"
    )
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    remarks = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return f"{self.material} x {self.quantity}"


# ---------------------------------------------------------------------------
# Purchase Order
# ---------------------------------------------------------------------------
class PurchaseOrder(TimeStampedModel):
    """A binding order issued to a vendor."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ISSUED = "ISSUED", "Issued"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially Received"
        RECEIVED = "RECEIVED", "Fully Received"
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=20, unique=True, editable=False)
    vendor = models.ForeignKey(
        Vendor, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    requisition = models.ForeignKey(
        PurchaseRequisition,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    order_date = models.DateField(default=timezone.localdate)
    expected_delivery_date = models.DateField(null=True, blank=True)
    delivery_address = models.TextField(blank=True)
    payment_terms_days = models.PositiveIntegerField(default=30)
    terms_and_conditions = models.TextField(blank=True)

    # Money totals (denormalised, recomputed from lines).
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))

    created_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    approved_by = models.ForeignKey(
        USER,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_purchase_orders",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("PO")
        super().save(*args, **kwargs)

    def recalculate_totals(self, *, save: bool = True) -> None:
        subtotal = Decimal("0.00")
        tax = Decimal("0.00")
        for line in self.lines.all():
            subtotal += line.line_subtotal
            tax += line.line_tax
        self.subtotal = subtotal.quantize(TWO_PLACES)
        self.tax_amount = tax.quantize(TWO_PLACES)
        self.total = (self.subtotal + self.tax_amount).quantize(TWO_PLACES)
        if save:
            super().save(update_fields=["subtotal", "tax_amount", "total", "updated_at"])

    def refresh_receipt_status(self, *, save: bool = True) -> None:
        """Move the PO between ISSUED / PARTIALLY_RECEIVED / RECEIVED based on GRNs."""
        if self.status in {self.Status.DRAFT, self.Status.CANCELLED, self.Status.CLOSED}:
            return
        lines = list(self.lines.all())
        if not lines:
            return
        fully = all(line.received_quantity >= line.quantity for line in lines)
        any_received = any(line.received_quantity > 0 for line in lines)
        if fully:
            new_status = self.Status.RECEIVED
        elif any_received:
            new_status = self.Status.PARTIALLY_RECEIVED
        else:
            new_status = self.Status.ISSUED
        if new_status != self.status:
            self.status = new_status
            if save:
                super().save(update_fields=["status", "updated_at"])


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("18.00")
    )
    received_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal("0.000")
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.material} x {self.quantity} @ {self.unit_price}"

    @property
    def line_subtotal(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(TWO_PLACES)

    @property
    def line_tax(self) -> Decimal:
        return (self.line_subtotal * self.tax_rate / Decimal("100")).quantize(TWO_PLACES)

    @property
    def line_total(self) -> Decimal:
        return (self.line_subtotal + self.line_tax).quantize(TWO_PLACES)

    @property
    def pending_quantity(self) -> Decimal:
        return self.quantity - self.received_quantity


# ---------------------------------------------------------------------------
# Goods Receipt Note (GRN)
# ---------------------------------------------------------------------------
class GoodsReceiptNote(TimeStampedModel):
    """Records materials physically received against a purchase order."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=20, unique=True, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="grns"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    received_date = models.DateField(default=timezone.localdate)
    challan_number = models.CharField(max_length=40, blank=True)
    vehicle_number = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="grns"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("GRN")
        super().save(*args, **kwargs)


class GRNLine(models.Model):
    grn = models.ForeignKey(
        GoodsReceiptNote, on_delete=models.CASCADE, related_name="lines"
    )
    po_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="grn_lines"
    )
    received_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0"))]
    )
    accepted_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0"))]
    )
    rejected_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal("0.000")
    )
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.po_line.material} received {self.received_quantity}"


# ---------------------------------------------------------------------------
# Vendor Bill (3-way matching)
# ---------------------------------------------------------------------------
class VendorBill(TimeStampedModel):
    """A vendor's invoice, matched against the PO and received goods."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        MATCHED = "MATCHED", "Matched"
        APPROVED = "APPROVED", "Approved"
        PAID = "PAID", "Paid"
        DISPUTED = "DISPUTED", "Disputed"
        CANCELLED = "CANCELLED", "Cancelled"

    class MatchStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        MATCHED = "MATCHED", "Matched"
        EXCEPTION = "EXCEPTION", "Exception"

    number = models.CharField(max_length=20, unique=True, editable=False)
    vendor_invoice_number = models.CharField(max_length=60)
    vendor = models.ForeignKey(
        Vendor, on_delete=models.PROTECT, related_name="bills"
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="bills"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    match_status = models.CharField(
        max_length=12, choices=MatchStatus.choices, default=MatchStatus.PENDING
    )
    match_notes = models.TextField(blank=True)
    bill_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)

    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))

    created_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="bills"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "vendor_invoice_number"],
                name="unique_vendor_invoice_number",
            )
        ]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("BILL")
        super().save(*args, **kwargs)

    def recalculate_totals(self, *, save: bool = True) -> None:
        subtotal = Decimal("0.00")
        tax = Decimal("0.00")
        for line in self.lines.all():
            subtotal += line.line_subtotal
            tax += line.line_tax
        self.subtotal = subtotal.quantize(TWO_PLACES)
        self.tax_amount = tax.quantize(TWO_PLACES)
        self.total = (self.subtotal + self.tax_amount).quantize(TWO_PLACES)
        if save:
            super().save(update_fields=["subtotal", "tax_amount", "total", "updated_at"])


class VendorBillLine(models.Model):
    bill = models.ForeignKey(
        VendorBill, on_delete=models.CASCADE, related_name="lines"
    )
    po_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="bill_lines"
    )
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("18.00")
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.po_line.material} x {self.quantity} @ {self.unit_price}"

    @property
    def line_subtotal(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(TWO_PLACES)

    @property
    def line_tax(self) -> Decimal:
        return (self.line_subtotal * self.tax_rate / Decimal("100")).quantize(TWO_PLACES)

    @property
    def line_total(self) -> Decimal:
        return (self.line_subtotal + self.line_tax).quantize(TWO_PLACES)
