"""Forms for the server-rendered procurement frontend.

Header forms are ``StyledModelForm`` subclasses (Bootstrap classes auto-applied).
Line-item forms are exposed so views can build inline formsets with the right
``extra``/``initial`` and per-PO ``po_line`` querysets.
"""
from django import forms

from procurement.models import (
    ApprovalRule,
    Attachment,
    ContractLine,
    GoodsReceiptNote,
    GRNLine,
    Material,
    MaterialCategory,
    Payment,
    PaymentSchedule,
    Project,
    PurchaseContract,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    PurchaseReturn,
    PurchaseReturnLine,
    QCChecklistItem,
    QualityInspection,
    RequestForQuotation,
    RFQLine,
    SupplierAddress,
    SupplierBankAccount,
    SupplierContact,
    SupplierDocument,
    SupplierQuotation,
    SupplierQuotationLine,
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
            "code", "name", "gstin", "pan", "contact_person", "email", "phone",
            "website", "address", "payment_terms_days", "credit_limit",
            "rating", "notes", "is_active",
        ]


class SupplierContactForm(StyledModelForm):
    class Meta:
        model = SupplierContact
        fields = ["name", "designation", "email", "phone", "is_primary"]


class SupplierAddressForm(StyledModelForm):
    class Meta:
        model = SupplierAddress
        fields = ["kind", "line1", "line2", "city", "state", "pincode", "country", "is_default"]


class SupplierBankAccountForm(StyledModelForm):
    class Meta:
        model = SupplierBankAccount
        fields = ["account_name", "account_number", "bank_name", "branch", "ifsc", "is_default"]


class SupplierDocumentForm(StyledModelForm):
    class Meta:
        model = SupplierDocument
        fields = ["title", "kind", "file", "expiry_date"]
        widgets = {"expiry_date": _DATE}


class MaterialCategoryForm(StyledModelForm):
    class Meta:
        model = MaterialCategory
        fields = ["name", "parent"]


class AttachmentForm(StyledModelForm):
    class Meta:
        model = Attachment
        fields = ["title", "kind", "file"]


class ApprovalRuleForm(StyledModelForm):
    class Meta:
        model = ApprovalRule
        fields = ["name", "document_type", "level", "role_required",
                  "min_amount", "max_amount", "escalate_after_hours", "is_active"]

    def __init__(self, *args, **kwargs):
        from accounts.models import Role
        super().__init__(*args, **kwargs)
        self.fields["role_required"] = forms.ChoiceField(
            choices=Role.choices, label="Role required")
        style_form(self)


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


class RequestForQuotationForm(StyledModelForm):
    class Meta:
        model = RequestForQuotation
        fields = ["project", "requisition", "vendors", "issue_date",
                  "response_deadline", "terms", "notes"]
        widgets = {
            "issue_date": _DATE,
            "response_deadline": _DATE,
            "vendors": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vendors"].queryset = Vendor.objects.filter(is_active=True)
        self.fields["requisition"].queryset = PurchaseRequisition.objects.filter(
            status=PurchaseRequisition.Status.APPROVED)
        self.fields["requisition"].required = False


class RFQLineForm(StyledModelForm):
    class Meta:
        model = RFQLine
        fields = ["material", "quantity", "remarks"]


class SupplierQuotationForm(StyledModelForm):
    class Meta:
        model = SupplierQuotation
        fields = ["vendor", "quotation_date", "valid_until", "delivery_days",
                  "warranty_months", "payment_terms_days", "notes"]
        widgets = {"quotation_date": _DATE, "valid_until": _DATE}

    def __init__(self, *args, rfq=None, **kwargs):
        super().__init__(*args, **kwargs)
        if rfq is not None:
            invited = rfq.vendors.all()
            self.fields["vendor"].queryset = invited if invited.exists() else Vendor.objects.filter(is_active=True)


class SupplierQuotationLineForm(StyledModelForm):
    class Meta:
        model = SupplierQuotationLine
        fields = ["material", "quantity", "unit_price", "tax_rate"]


class QualityInspectionForm(StyledModelForm):
    class Meta:
        model = QualityInspection
        fields = ["remarks"]


class QCChecklistItemForm(StyledModelForm):
    class Meta:
        model = QCChecklistItem
        fields = ["description", "result", "remarks"]


class PurchaseOrderForm(StyledModelForm):
    class Meta:
        model = PurchaseOrder
        fields = [
            "vendor", "project", "requisition", "contract", "order_date",
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


class PurchaseReturnForm(StyledModelForm):
    class Meta:
        model = PurchaseReturn
        fields = ["resolution", "return_date", "reason", "credit_note_number"]
        widgets = {"return_date": _DATE}


class PurchaseReturnLineForm(StyledModelForm):
    class Meta:
        model = PurchaseReturnLine
        fields = ["po_line", "quantity", "remarks"]


class PurchaseContractForm(StyledModelForm):
    class Meta:
        model = PurchaseContract
        fields = ["title", "vendor", "contract_type", "start_date", "end_date",
                  "total_value", "auto_renew", "terms"]
        widgets = {"start_date": _DATE, "end_date": _DATE}


class ContractLineForm(StyledModelForm):
    class Meta:
        model = ContractLine
        fields = ["material", "unit_price", "tax_rate", "max_quantity"]


class PaymentForm(StyledModelForm):
    class Meta:
        model = Payment
        fields = ["vendor", "bill", "purchase_order", "payment_type", "method",
                  "amount", "payment_date", "reference", "notes"]
        widgets = {"payment_date": _DATE}


class PaymentScheduleForm(StyledModelForm):
    class Meta:
        model = PaymentSchedule
        fields = ["vendor", "bill", "due_date", "amount", "note"]
        widgets = {"due_date": _DATE}


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
