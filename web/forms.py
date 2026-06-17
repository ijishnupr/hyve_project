"""Forms for the server-rendered procurement frontend.

Header forms are ``StyledModelForm`` subclasses (Bootstrap classes auto-applied).
Line-item forms are exposed so views can build inline formsets with the right
``extra``/``initial`` and per-PO ``po_line`` querysets.
"""
from django import forms

from procurement.models import (
    GRNLine,
    GoodsReceiptNote,
    Material,
    MaterialCategory,
    Project,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)


def style_form(form):
    """Apply Bootstrap form classes to every widget on a (bound or unbound) form."""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            widget.attrs.setdefault("class", "form-select form-select-sm")
        elif isinstance(widget, forms.Textarea):
            widget.attrs.setdefault("class", "form-control form-control-sm")
            widget.attrs.setdefault("rows", 2)
        else:
            widget.attrs.setdefault("class", "form-control form-control-sm")


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        style_form(self)


_DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
class ProjectForm(StyledModelForm):
    class Meta:
        model = Project
        fields = [
            "code", "name", "location", "status", "budget",
            "start_date", "end_date", "manager",
        ]
        widgets = {"start_date": _DATE, "end_date": _DATE}


class VendorForm(StyledModelForm):
    class Meta:
        model = Vendor
        fields = [
            "code", "name", "gstin", "contact_person", "email", "phone",
            "address", "payment_terms_days", "rating", "is_active",
        ]


class MaterialCategoryForm(StyledModelForm):
    class Meta:
        model = MaterialCategory
        fields = ["name", "parent"]


class MaterialForm(StyledModelForm):
    class Meta:
        model = Material
        fields = [
            "code", "name", "category", "unit", "hsn_code",
            "default_tax_rate", "specification", "is_active",
        ]


# ---------------------------------------------------------------------------
# Document header forms
# ---------------------------------------------------------------------------
class PurchaseRequisitionForm(StyledModelForm):
    class Meta:
        model = PurchaseRequisition
        fields = ["project", "required_by", "notes"]
        widgets = {"required_by": _DATE}


class PurchaseOrderForm(StyledModelForm):
    class Meta:
        model = PurchaseOrder
        fields = [
            "vendor", "project", "requisition", "order_date",
            "expected_delivery_date", "delivery_address",
            "payment_terms_days", "terms_and_conditions",
        ]
        widgets = {"order_date": _DATE, "expected_delivery_date": _DATE}


class GoodsReceiptNoteForm(StyledModelForm):
    class Meta:
        model = GoodsReceiptNote
        fields = ["received_date", "challan_number", "vehicle_number", "notes"]
        widgets = {"received_date": _DATE}


class VendorBillForm(StyledModelForm):
    class Meta:
        model = VendorBill
        fields = ["vendor_invoice_number", "bill_date", "due_date"]
        widgets = {"bill_date": _DATE, "due_date": _DATE}


# ---------------------------------------------------------------------------
# Line-item forms (used to build inline formsets in views)
# ---------------------------------------------------------------------------
class PurchaseRequisitionLineForm(StyledModelForm):
    class Meta:
        model = PurchaseRequisitionLine
        fields = ["material", "quantity", "remarks"]


class PurchaseOrderLineForm(StyledModelForm):
    class Meta:
        model = PurchaseOrderLine
        fields = ["material", "quantity", "unit_price", "tax_rate"]


class GRNLineForm(StyledModelForm):
    class Meta:
        model = GRNLine
        fields = [
            "po_line", "received_quantity", "accepted_quantity",
            "rejected_quantity", "remarks",
        ]


class VendorBillLineForm(StyledModelForm):
    class Meta:
        model = VendorBillLine
        fields = ["po_line", "quantity", "unit_price", "tax_rate"]
