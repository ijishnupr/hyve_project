"""
Domain models for construction procurement.

Flow:  Purchase Requisition  ->  Purchase Order  ->  Goods Receipt (GRN)
       ->  Vendor Bill (3-way matched against PO + GRN).

Master data: Project (site), Vendor, MaterialCategory, Material.
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
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
    pan = models.CharField("PAN", max_length=10, blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    address = models.TextField(blank=True)
    payment_terms_days = models.PositiveIntegerField(
        default=30, help_text="Default net payment terms in days."
    )
    credit_limit = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00"),
        help_text="Maximum outstanding credit allowed for this supplier.",
    )
    rating = models.PositiveSmallIntegerField(
        default=0, help_text="Performance rating 0-5."
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class SupplierContact(TimeStampedModel):
    """A named contact person at a supplier."""

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=120)
    designation = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.vendor.code})"


class SupplierAddress(TimeStampedModel):
    """A structured address for a supplier (billing / shipping / office / factory)."""

    class Kind(models.TextChoices):
        BILLING = "BILLING", "Billing"
        SHIPPING = "SHIPPING", "Shipping"
        OFFICE = "OFFICE", "Office"
        FACTORY = "FACTORY", "Factory / Works"

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="addresses")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OFFICE)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    country = models.CharField(max_length=120, default="India")
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "kind"]
        verbose_name_plural = "supplier addresses"

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.line1}, {self.city}"


class SupplierBankAccount(TimeStampedModel):
    """Bank details used to pay a supplier."""

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="bank_accounts")
    account_name = models.CharField(max_length=200)
    account_number = models.CharField(max_length=40)
    bank_name = models.CharField(max_length=200)
    branch = models.CharField(max_length=200, blank=True)
    ifsc = models.CharField("IFSC", max_length=15, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "bank_name"]

    def __str__(self) -> str:
        return f"{self.bank_name} — {self.account_number}"


class SupplierDocument(TimeStampedModel):
    """A file attached to a supplier (GST cert, PAN, MSME, agreement, ...)."""

    class Kind(models.TextChoices):
        GST = "GST", "GST Certificate"
        PAN = "PAN", "PAN Card"
        MSME = "MSME", "MSME / Udyam"
        CHEQUE = "CHEQUE", "Cancelled Cheque"
        AGREEMENT = "AGREEMENT", "Agreement"
        OTHER = "OTHER", "Other"

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.OTHER)
    file = models.FileField(upload_to="supplier_docs/")
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["kind", "title"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title}"


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
    contract = models.ForeignKey(
        "PurchaseContract",
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
    revision = models.PositiveSmallIntegerField(
        default=0, help_text="Bumped each time an issued PO is re-opened and amended."
    )
    emailed_at = models.DateTimeField(null=True, blank=True)

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

    @property
    def amount_paid(self) -> Decimal:
        paid = sum(
            (p.amount for p in self.payments.all() if p.status == "PAID"),
            Decimal("0.00"),
        )
        return paid.quantize(TWO_PLACES)

    @property
    def outstanding(self) -> Decimal:
        return (self.total - self.amount_paid).quantize(TWO_PLACES)


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


# ---------------------------------------------------------------------------
# Request for Quotation (RFQ)
# ---------------------------------------------------------------------------
class RequestForQuotation(TimeStampedModel):
    """An enquiry sent to one or more suppliers asking them to quote."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent to Suppliers"
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=20, unique=True, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="rfqs"
    )
    requisition = models.ForeignKey(
        PurchaseRequisition,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rfqs",
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT
    )
    vendors = models.ManyToManyField(Vendor, related_name="rfqs", blank=True)
    issue_date = models.DateField(default=timezone.localdate)
    response_deadline = models.DateField(
        null=True, blank=True, help_text="Quotations received after this date may be ignored."
    )
    terms = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="rfqs"
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "request for quotation"

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("RFQ")
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return bool(self.response_deadline and self.response_deadline < timezone.localdate())


class RFQLine(models.Model):
    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.CASCADE, related_name="lines"
    )
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))]
    )
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.material} x {self.quantity}"


# ---------------------------------------------------------------------------
# Supplier Quotation (response to an RFQ) + comparison
# ---------------------------------------------------------------------------
class SupplierQuotation(TimeStampedModel):
    """A supplier's priced response to an RFQ, used for comparison/selection."""

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        SELECTED = "SELECTED", "Selected (won)"
        REJECTED = "REJECTED", "Rejected"

    number = models.CharField(max_length=20, unique=True, editable=False)
    rfq = models.ForeignKey(
        RequestForQuotation, on_delete=models.CASCADE, related_name="quotations"
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.PROTECT, related_name="quotations"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.RECEIVED
    )
    quotation_date = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(null=True, blank=True)
    delivery_days = models.PositiveIntegerField(
        default=0, help_text="Promised lead time in days."
    )
    warranty_months = models.PositiveIntegerField(default=0)
    payment_terms_days = models.PositiveIntegerField(default=30)
    notes = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))

    # The PO created when this quotation is selected (if any).
    purchase_order = models.ForeignKey(
        "PurchaseOrder", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="source_quotations",
    )
    created_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="quotations"
    )

    class Meta:
        ordering = ["total"]
        constraints = [
            models.UniqueConstraint(
                fields=["rfq", "vendor"], name="unique_quotation_per_rfq_vendor"
            )
        ]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("QUO")
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


class SupplierQuotationLine(models.Model):
    quotation = models.ForeignKey(
        SupplierQuotation, on_delete=models.CASCADE, related_name="lines"
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


# ---------------------------------------------------------------------------
# Approval workflow (matrix / multi-level / thresholds / escalation)
# ---------------------------------------------------------------------------
class ApprovalDocumentType(models.TextChoices):
    PURCHASE_REQUISITION = "PURCHASE_REQUISITION", "Purchase Requisition"
    PURCHASE_ORDER = "PURCHASE_ORDER", "Purchase Order"
    VENDOR_BILL = "VENDOR_BILL", "Vendor Bill"
    PURCHASE_CONTRACT = "PURCHASE_CONTRACT", "Purchase Contract"


class ApprovalRule(TimeStampedModel):
    """One row of the approval matrix: a level + role that must sign off when a
    document's value falls in ``[min_amount, max_amount]``."""

    name = models.CharField(max_length=120)
    document_type = models.CharField(max_length=32, choices=ApprovalDocumentType.choices)
    level = models.PositiveSmallIntegerField(
        default=1, help_text="Approval order; level 1 approves first."
    )
    role_required = models.CharField(
        max_length=32, help_text="accounts.Role value that may approve this level."
    )
    min_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    max_amount = models.DecimalField(
        max_digits=16, decimal_places=2, null=True, blank=True,
        help_text="Upper bound of the band; blank means no upper limit.",
    )
    escalate_after_hours = models.PositiveIntegerField(
        default=0, help_text="Flag the step as overdue after this many hours (0 = never)."
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["document_type", "level", "min_amount"]

    def __str__(self) -> str:
        return f"{self.get_document_type_display()} L{self.level} — {self.name}"

    def matches_amount(self, amount: Decimal) -> bool:
        if amount < self.min_amount:
            return False
        if self.max_amount is not None and amount > self.max_amount:
            return False
        return True


class ApprovalRequest(TimeStampedModel):
    """An approval process instance attached to any document via a generic FK."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    document = GenericForeignKey("content_type", "object_id")

    document_type = models.CharField(max_length=32, choices=ApprovalDocumentType.choices)
    amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    current_level = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self) -> str:
        return f"Approval#{self.pk} {self.document_type} ({self.get_status_display()})"


class ApprovalStep(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        SKIPPED = "SKIPPED", "Skipped"

    request = models.ForeignKey(
        ApprovalRequest, on_delete=models.CASCADE, related_name="steps"
    )
    level = models.PositiveSmallIntegerField()
    role_required = models.CharField(max_length=32)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    acted_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="approval_steps"
    )
    acted_at = models.DateTimeField(null=True, blank=True)
    comments = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["level", "id"]

    def __str__(self) -> str:
        return f"L{self.level} {self.role_required} ({self.get_status_display()})"

    @property
    def is_overdue(self) -> bool:
        return bool(
            self.status == self.Status.PENDING
            and self.due_at
            and self.due_at < timezone.now()
        )


# ---------------------------------------------------------------------------
# Purchase Order revision history
# ---------------------------------------------------------------------------
class PurchaseOrderRevision(models.Model):
    """An immutable snapshot of a PO's value captured each time it is issued."""

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="revisions"
    )
    revision = models.PositiveSmallIntegerField()
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal("0.00"))
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="po_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-revision", "-created_at"]

    def __str__(self) -> str:
        return f"{self.purchase_order.number} rev {self.revision}"


# ---------------------------------------------------------------------------
# Generic attachments (usable on any document)
# ---------------------------------------------------------------------------
class Attachment(TimeStampedModel):
    """A file attached to any procurement document via a generic FK."""

    class Kind(models.TextChoices):
        QUOTATION = "QUOTATION", "Quotation"
        PO_PDF = "PO_PDF", "Purchase Order PDF"
        DELIVERY_NOTE = "DELIVERY_NOTE", "Delivery Note"
        INVOICE = "INVOICE", "Invoice"
        INSPECTION = "INSPECTION", "Inspection Report"
        OTHER = "OTHER", "Other"

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    document = GenericForeignKey("content_type", "object_id")

    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.OTHER)
    file = models.FileField(upload_to="attachments/")
    uploaded_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title}"


# ---------------------------------------------------------------------------
# Inventory — Stock Ledger integration
# ---------------------------------------------------------------------------
class StockItem(TimeStampedModel):
    """Running on-hand balance of a material at a project/site."""

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="stock_items")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="stock_items")
    quantity_on_hand = models.DecimalField(
        max_digits=16, decimal_places=3, default=Decimal("0.000")
    )

    class Meta:
        ordering = ["project", "material"]
        constraints = [
            models.UniqueConstraint(fields=["material", "project"], name="unique_stock_item")
        ]

    def __str__(self) -> str:
        return f"{self.material} @ {self.project}: {self.quantity_on_hand}"


class StockLedgerEntry(TimeStampedModel):
    """An immutable inventory movement. Positive = in, negative = out."""

    class Movement(models.TextChoices):
        RECEIPT = "RECEIPT", "Goods Receipt"
        RETURN = "RETURN", "Purchase Return"
        ISSUE = "ISSUE", "Issue / Consumption"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment / Reversal"

    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="ledger_entries")
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="ledger_entries")
    movement = models.CharField(max_length=12, choices=Movement.choices)
    quantity = models.DecimalField(
        max_digits=16, decimal_places=3,
        help_text="Signed movement: positive increases stock, negative decreases it.",
    )
    balance_after = models.DecimalField(max_digits=16, decimal_places=3, default=Decimal("0.000"))
    remarks = models.CharField(max_length=255, blank=True)

    # Source document (GRN, PurchaseReturn, ...).
    content_type = models.ForeignKey(
        ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source = GenericForeignKey("content_type", "object_id")

    created_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="ledger_entries")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["material", "project"])]

    def __str__(self) -> str:
        return f"{self.get_movement_display()} {self.quantity} {self.material}"


# ---------------------------------------------------------------------------
# Quality Inspection (against a Goods Receipt)
# ---------------------------------------------------------------------------
class QualityInspection(TimeStampedModel):
    """A QC inspection performed on materials received in a GRN."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PASSED = "PASSED", "Passed"
        FAILED = "FAILED", "Failed"

    number = models.CharField(max_length=20, unique=True, editable=False)
    grn = models.ForeignKey(
        GoodsReceiptNote, on_delete=models.CASCADE, related_name="inspections"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    inspected_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL, related_name="inspections"
    )
    inspected_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("QC")
        super().save(*args, **kwargs)


class QCChecklistItem(models.Model):
    class Result(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PASS = "PASS", "Pass"
        FAIL = "FAIL", "Fail"
        NA = "NA", "Not applicable"

    inspection = models.ForeignKey(
        QualityInspection, on_delete=models.CASCADE, related_name="items"
    )
    description = models.CharField(max_length=255)
    result = models.CharField(max_length=8, choices=Result.choices, default=Result.PENDING)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.description}: {self.get_result_display()}"


# ---------------------------------------------------------------------------
# Supplier Payments
# ---------------------------------------------------------------------------
class Payment(TimeStampedModel):
    """A payment made to a supplier — an advance or against a vendor bill."""

    class Type(models.TextChoices):
        ADVANCE = "ADVANCE", "Advance"
        AGAINST_BILL = "AGAINST_BILL", "Against Bill"

    class Method(models.TextChoices):
        BANK_TRANSFER = "BANK_TRANSFER", "Bank Transfer"
        CHEQUE = "CHEQUE", "Cheque"
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    number = models.CharField(max_length=20, unique=True, editable=False)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="payments")
    bill = models.ForeignKey(
        VendorBill, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    payment_type = models.CharField(max_length=16, choices=Type.choices, default=Type.AGAINST_BILL)
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.BANK_TRANSFER)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(
        max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    payment_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=80, blank=True, help_text="Txn / cheque / UTR number.")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="payments")

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.number} — {self.vendor.name} {self.amount}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("PAY")
        super().save(*args, **kwargs)


class PaymentSchedule(TimeStampedModel):
    """A planned instalment due to a supplier (payment schedule)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="payment_schedules")
    bill = models.ForeignKey(
        VendorBill, null=True, blank=True, on_delete=models.CASCADE, related_name="schedules")
    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.CASCADE, related_name="schedules")
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["due_date"]

    def __str__(self) -> str:
        return f"{self.vendor.name} — {self.amount} due {self.due_date}"

    @property
    def is_overdue(self) -> bool:
        return bool(self.status == self.Status.PENDING and self.due_date < timezone.localdate())


# ---------------------------------------------------------------------------
# Purchase Returns
# ---------------------------------------------------------------------------
class PurchaseReturn(TimeStampedModel):
    """Return of received materials to a supplier (damaged / rejected)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CANCELLED = "CANCELLED", "Cancelled"

    class Resolution(models.TextChoices):
        REPLACEMENT = "REPLACEMENT", "Replacement"
        REFUND = "REFUND", "Refund"
        CREDIT_NOTE = "CREDIT_NOTE", "Credit Note"

    number = models.CharField(max_length=20, unique=True, editable=False)
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="returns")
    grn = models.ForeignKey(
        GoodsReceiptNote, null=True, blank=True, on_delete=models.SET_NULL, related_name="returns")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="returns")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    resolution = models.CharField(
        max_length=12, choices=Resolution.choices, default=Resolution.CREDIT_NOTE)
    return_date = models.DateField(default=timezone.localdate)
    reason = models.TextField(blank=True)
    credit_note_number = models.CharField(max_length=60, blank=True)
    created_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="returns")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("RET")
        super().save(*args, **kwargs)


class PurchaseReturnLine(models.Model):
    purchase_return = models.ForeignKey(
        PurchaseReturn, on_delete=models.CASCADE, related_name="lines")
    po_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="return_lines")
    quantity = models.DecimalField(
        max_digits=14, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.po_line.material} x {self.quantity}"


# ---------------------------------------------------------------------------
# Purchase Contracts (blanket orders / rate contracts)
# ---------------------------------------------------------------------------
class PurchaseContract(TimeStampedModel):
    """A long-term agreement / blanket order with agreed pricing."""

    class Type(models.TextChoices):
        BLANKET = "BLANKET", "Blanket Order"
        RATE = "RATE", "Rate Contract"
        SERVICE = "SERVICE", "Service Agreement"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        TERMINATED = "TERMINATED", "Terminated"
        RENEWED = "RENEWED", "Renewed"

    number = models.CharField(max_length=20, unique=True, editable=False)
    title = models.CharField(max_length=200)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="contracts")
    contract_type = models.CharField(max_length=10, choices=Type.choices, default=Type.BLANKET)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField()
    end_date = models.DateField()
    total_value = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00"),
        help_text="Ceiling value of the blanket order (0 = uncapped).")
    consumed_value = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00"))
    auto_renew = models.BooleanField(default=False)
    renewed_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewals")
    terms = models.TextField(blank=True)
    created_by = models.ForeignKey(
        USER, on_delete=models.PROTECT, related_name="contracts")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.number} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = DocumentCounter.next_number("CON")
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return self.end_date < timezone.localdate()

    @property
    def remaining_value(self) -> Decimal:
        if self.total_value <= 0:
            return Decimal("0.00")
        return (self.total_value - self.consumed_value).quantize(TWO_PLACES)


class ContractLine(models.Model):
    """Agreed price for a material under a contract."""

    contract = models.ForeignKey(
        PurchaseContract, on_delete=models.CASCADE, related_name="lines")
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    unit_price = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"))
    max_quantity = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True,
        help_text="Optional cap on the quantity that may be ordered under this contract.")

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.material} @ {self.unit_price}"
