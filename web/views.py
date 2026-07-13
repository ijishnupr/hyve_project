"""Server-rendered views for the procurement frontend.

Thin layer over ``procurement.services`` — all state transitions delegate to the
service functions (the same ones the API uses), so the business rules live in one
place. Permissions mirror the DRF permission classes via role predicates on User.
"""
from decimal import Decimal
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Sum
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from procurement import analytics, reports, services
from procurement.models import (
    ApprovalRule,
    ApprovalStep,
    Attachment,
    AuditLog,
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
    StockItem,
    StockLedgerEntry,
    SupplierQuotation,
    SupplierQuotationLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)

from .forms import (
    ApprovalRuleForm,
    AttachmentForm,
    ContractLineForm,
    GoodsReceiptNoteForm,
    GRNLineForm,
    MaterialCategoryForm,
    MaterialForm,
    PaymentForm,
    PaymentScheduleForm,
    ProjectForm,
    PurchaseContractForm,
    PurchaseOrderForm,
    PurchaseOrderLineForm,
    PurchaseRequisitionForm,
    PurchaseRequisitionLineForm,
    PurchaseReturnForm,
    PurchaseReturnLineForm,
    QCChecklistItemForm,
    QualityInspectionForm,
    RequestForQuotationForm,
    RFQLineForm,
    SupplierAddressForm,
    SupplierBankAccountForm,
    SupplierContactForm,
    SupplierDocumentForm,
    SupplierQuotationForm,
    SupplierQuotationLineForm,
    VendorBillForm,
    VendorBillLineForm,
    VendorForm,
    style_form,
)


# ---------------------------------------------------------------------------
# Auth & permissions
# ---------------------------------------------------------------------------
def login_view(request):
    if request.user.is_authenticated:
        return redirect("web:dashboard")
    form = AuthenticationForm(request, data=request.POST or None)
    style_form(form)
    if request.method == "POST" and form.is_valid():
        auth_login(request, form.get_user())
        messages.success(request, f"Welcome, {form.get_user().get_username()}.")
        return redirect(request.GET.get("next") or "web:dashboard")
    return render(request, "web/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    messages.info(request, "Signed out.")
    return redirect("web:login")


def role_required(predicate):
    """Gate a view on a User role predicate (e.g. 'can_manage_procurement')."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if not getattr(request.user, predicate, False):
                messages.error(request, "You don't have permission for that action.")
                return redirect(request.META.get("HTTP_REFERER") or "web:dashboard")
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def _run(request, fn, *args, success="Done.", **kwargs):
    """Execute a service transition, surfacing TransitionError as a message."""
    try:
        fn(*args, **kwargs)
        messages.success(request, success)
    except services.TransitionError as exc:
        messages.error(request, str(exc))


# ---------------------------------------------------------------------------
# PDF rendering + generic attachments
# ---------------------------------------------------------------------------
def _render_pdf(request, template, context, filename):
    """Render an HTML template to a downloadable PDF via WeasyPrint."""
    from weasyprint import HTML

    context.setdefault("now", timezone.now())
    html = render_to_string(template, context, request=request)
    pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


@login_required
def attachment_add(request, model, object_id):
    """Attach an uploaded file to any document identified by (model, object_id)."""
    if not request.user.can_manage_procurement and not request.user.can_manage_bills:
        messages.error(request, "You don't have permission to add attachments.")
        return redirect(request.META.get("HTTP_REFERER") or "web:dashboard")
    ct = get_object_or_404(ContentType, model=model, app_label="procurement")
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        att = form.save(commit=False)
        att.content_type = ct
        att.object_id = object_id
        att.uploaded_by = request.user
        att.save()
        messages.success(request, "Attachment uploaded.")
    else:
        messages.error(request, f"Upload failed: {form.errors.as_text()}")
    return redirect(request.META.get("HTTP_REFERER") or "web:dashboard")


@login_required
def attachment_delete(request, pk):
    att = get_object_or_404(Attachment, pk=pk)
    if not request.user.can_manage_procurement and not request.user.can_manage_bills:
        messages.error(request, "You don't have permission to remove attachments.")
    else:
        att.delete()
        messages.info(request, "Attachment removed.")
    return redirect(request.META.get("HTTP_REFERER") or "web:dashboard")


def attachments_for(obj):
    """Return the queryset of attachments for a model instance."""
    ct = ContentType.objects.get_for_model(type(obj))
    return Attachment.objects.filter(content_type=ct, object_id=obj.pk)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def _status_counts(model):
    return {
        row["status"]: row["n"]
        for row in model.objects.values("status").annotate(n=Count("id"))
    }


def _sum(qs):
    return qs.aggregate(s=Sum("total"))["s"] or 0


@login_required
def dashboard(request):
    POStatus = PurchaseOrder.Status
    BillStatus = VendorBill.Status

    # Money in flight across the procure-to-pay cycle.
    open_po_value = _sum(PurchaseOrder.objects.filter(
        status__in=[POStatus.ISSUED, POStatus.PARTIALLY_RECEIVED]))
    committed_value = _sum(PurchaseOrder.objects.exclude(
        status__in=[POStatus.DRAFT, POStatus.CANCELLED]))
    payable_value = _sum(VendorBill.objects.filter(
        status__in=[BillStatus.MATCHED, BillStatus.APPROVED]))
    paid_value = _sum(VendorBill.objects.filter(status=BillStatus.PAID))

    # A cross-document "needs attention" queue for approvers/accountants.
    attention = []
    for pr in PurchaseRequisition.objects.filter(
            status=PurchaseRequisition.Status.SUBMITTED).select_related("project")[:6]:
        attention.append({"kind": "Requisition", "icon": "bi-file-earmark-text",
                          "number": pr.number, "detail": pr.project.name,
                          "action": "Awaiting approval", "color": "amber",
                          "url": reverse("web:pr_detail", args=[pr.pk])})
    for bill in VendorBill.objects.filter(
            status=BillStatus.DISPUTED).select_related("vendor")[:6]:
        attention.append({"kind": "Vendor bill", "icon": "bi-receipt",
                          "number": bill.number, "detail": bill.vendor.name,
                          "action": "3-way match exception", "color": "red",
                          "url": reverse("web:bill_detail", args=[bill.pk])})
    for bill in VendorBill.objects.filter(
            status=BillStatus.MATCHED).select_related("vendor")[:6]:
        attention.append({"kind": "Vendor bill", "icon": "bi-receipt",
                          "number": bill.number, "detail": bill.vendor.name,
                          "action": "Ready to approve", "color": "blue",
                          "url": reverse("web:bill_detail", args=[bill.pk])})

    trend = analytics.monthly_spend(6)
    trend_max = max((r["total"] for r in trend), default=Decimal("0")) or Decimal("1")
    trend_bars = [{
        "month": r["month"], "total": r["total"],
        "pct": int(min(100, (r["total"] / trend_max) * 100)),
    } for r in trend]

    ctx = {
        "counts": {
            "projects": Project.objects.count(),
            "vendors": Vendor.objects.count(),
            "materials": Material.objects.count(),
            "requisitions": PurchaseRequisition.objects.count(),
            "purchase_orders": PurchaseOrder.objects.count(),
            "grns": GoodsReceiptNote.objects.count(),
            "bills": VendorBill.objects.count(),
        },
        "money": {
            "open_po": open_po_value,
            "committed": committed_value,
            "payable": payable_value,
            "paid": paid_value,
        },
        "pending": analytics.pending_counts(),
        "top_suppliers": analytics.top_suppliers(5),
        "trend_bars": trend_bars,
        "pr_status": _status_counts(PurchaseRequisition),
        "po_status": _status_counts(PurchaseOrder),
        "bill_status": _status_counts(VendorBill),
        "attention": attention[:8],
        "recent_prs": PurchaseRequisition.objects.select_related("project")[:5],
        "recent_pos": PurchaseOrder.objects.select_related("vendor", "project")[:5],
        "recent_bills": VendorBill.objects.select_related("vendor")[:5],
    }
    return render(request, "web/dashboard.html", ctx)


@login_required
def analytics_view(request):
    return render(request, "web/analytics.html", {
        "monthly": analytics.monthly_spend(12),
        "top_suppliers": analytics.top_suppliers(10),
        "categories": analytics.category_spend(),
        "performance": analytics.supplier_performance(),
    })


# ---------------------------------------------------------------------------
# Master data — generic list/create/edit
# ---------------------------------------------------------------------------
def _master_list(request, *, title, queryset, headers, row_fn, new_url, edit_name, can_edit):
    rows = []
    for obj in queryset:
        rows.append({
            "cells": row_fn(obj),
            "edit_url": reverse(edit_name, args=[obj.pk]) if can_edit else None,
        })
    return render(request, "web/master_list.html", {
        "title": title, "headers": headers, "rows": rows,
        "new_url": new_url if can_edit else None,
    })


def _master_form(request, *, title, form_class, instance=None, list_name):
    form = form_class(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{title} saved.")
        return redirect(list_name)
    return render(request, "web/master_form.html", {"title": title, "form": form})


@login_required
def project_list(request):
    return _master_list(
        request, title="Projects", queryset=Project.objects.all(),
        headers=["Code", "Name", "Location", "Status", "Budget"],
        row_fn=lambda o: [o.code, o.name, o.location, o.get_status_display(), o.budget],
        new_url=reverse("web:project_new"), edit_name="web:project_edit",
        can_edit=request.user.can_manage_procurement,
    )


@role_required("can_manage_procurement")
def project_new(request):
    return _master_form(request, title="New Project", form_class=ProjectForm, list_name="web:project_list")


@role_required("can_manage_procurement")
def project_edit(request, pk):
    return _master_form(request, title="Edit Project", form_class=ProjectForm,
                        instance=get_object_or_404(Project, pk=pk), list_name="web:project_list")


@login_required
def vendor_list(request):
    vendors = Vendor.objects.all()
    return render(request, "web/vendor_list.html", {
        "vendors": vendors, "can_edit": request.user.can_manage_procurement})


@login_required
def vendor_detail(request, pk):
    vendor = get_object_or_404(
        Vendor.objects.prefetch_related(
            "contacts", "addresses", "bank_accounts", "documents"), pk=pk)
    can_edit = request.user.can_manage_procurement
    return render(request, "web/vendor_detail.html", {
        "vendor": vendor, "can_edit": can_edit,
        "contact_form": SupplierContactForm(),
        "address_form": SupplierAddressForm(),
        "bank_form": SupplierBankAccountForm(),
        "document_form": SupplierDocumentForm(),
    })


@role_required("can_manage_procurement")
def vendor_new(request):
    return _master_form(request, title="New Vendor", form_class=VendorForm, list_name="web:vendor_list")


@role_required("can_manage_procurement")
def vendor_edit(request, pk):
    return _master_form(request, title="Edit Vendor", form_class=VendorForm,
                        instance=get_object_or_404(Vendor, pk=pk), list_name="web:vendor_list")


# -- supplier child records (contacts / addresses / banks / documents) --------
_VENDOR_CHILD_FORMS = {
    "contact": (SupplierContactForm, "contacts", "Contact"),
    "address": (SupplierAddressForm, "addresses", "Address"),
    "bank": (SupplierBankAccountForm, "bank_accounts", "Bank account"),
    "document": (SupplierDocumentForm, "documents", "Document"),
}


@role_required("can_manage_procurement")
def vendor_child_add(request, pk, kind):
    vendor = get_object_or_404(Vendor, pk=pk)
    form_class, related_name, label = _VENDOR_CHILD_FORMS[kind]
    form = form_class(request.POST, request.FILES or None)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.vendor = vendor
        obj.save()
        messages.success(request, f"{label} added.")
    else:
        messages.error(request, f"Could not add {label.lower()}: {form.errors.as_text()}")
    return redirect("web:vendor_detail", pk=pk)


@role_required("can_manage_procurement")
def vendor_child_delete(request, pk, kind, child_pk):
    _form_class, related_name, label = _VENDOR_CHILD_FORMS[kind]
    vendor = get_object_or_404(Vendor, pk=pk)
    get_object_or_404(getattr(vendor, related_name), pk=child_pk).delete()
    messages.info(request, f"{label} removed.")
    return redirect("web:vendor_detail", pk=pk)


@login_required
def category_list(request):
    return _master_list(
        request, title="Material Categories", queryset=MaterialCategory.objects.all(),
        headers=["Name", "Parent"],
        row_fn=lambda o: [o.name, o.parent or "—"],
        new_url=reverse("web:category_new"), edit_name="web:category_edit",
        can_edit=request.user.can_manage_procurement,
    )


@role_required("can_manage_procurement")
def category_new(request):
    return _master_form(request, title="New Category", form_class=MaterialCategoryForm, list_name="web:category_list")


@role_required("can_manage_procurement")
def category_edit(request, pk):
    return _master_form(request, title="Edit Category", form_class=MaterialCategoryForm,
                        instance=get_object_or_404(MaterialCategory, pk=pk), list_name="web:category_list")


@login_required
def material_list(request):
    return _master_list(
        request, title="Materials", queryset=Material.objects.select_related("category"),
        headers=["Code", "Name", "Category", "Unit", "HSN", "Tax %", "Active"],
        row_fn=lambda o: [o.code, o.name, o.category or "—", o.get_unit_display(),
                          o.hsn_code, o.default_tax_rate, "Yes" if o.is_active else "No"],
        new_url=reverse("web:material_new"), edit_name="web:material_edit",
        can_edit=request.user.can_manage_procurement,
    )


@role_required("can_manage_procurement")
def material_new(request):
    return _master_form(request, title="New Material", form_class=MaterialForm, list_name="web:material_list")


@role_required("can_manage_procurement")
def material_edit(request, pk):
    return _master_form(request, title="Edit Material", form_class=MaterialForm,
                        instance=get_object_or_404(Material, pk=pk), list_name="web:material_list")


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------
@login_required
def approval_rule_list(request):
    return _master_list(
        request, title="Approval Matrix", queryset=ApprovalRule.objects.all(),
        headers=["Name", "Document", "Level", "Role", "Min", "Max", "Active"],
        row_fn=lambda o: [o.name, o.get_document_type_display(), o.level, o.role_required,
                          o.min_amount, o.max_amount if o.max_amount is not None else "∞",
                          "Yes" if o.is_active else "No"],
        new_url=reverse("web:approval_rule_new"), edit_name="web:approval_rule_edit",
        can_edit=request.user.can_manage_procurement,
    )


@role_required("can_manage_procurement")
def approval_rule_new(request):
    return _master_form(request, title="New Approval Rule", form_class=ApprovalRuleForm,
                        list_name="web:approval_rule_list")


@role_required("can_manage_procurement")
def approval_rule_edit(request, pk):
    return _master_form(request, title="Edit Approval Rule", form_class=ApprovalRuleForm,
                        instance=get_object_or_404(ApprovalRule, pk=pk),
                        list_name="web:approval_rule_list")


@login_required
def approval_inbox(request):
    steps = services.pending_steps_for_user(request.user)
    # Attach the linked document for display.
    rows = [{"step": s, "document": s.request.document} for s in steps]
    return render(request, "web/approval_inbox.html", {"rows": rows})


@login_required
def approval_step_approve(request, pk):
    step = get_object_or_404(ApprovalStep, pk=pk)
    _run(request, services.approve_step, step, user=request.user,
         comments=request.POST.get("comments", ""), success="Approval recorded.")
    return redirect("web:approval_inbox")


@login_required
def approval_step_reject(request, pk):
    step = get_object_or_404(ApprovalStep, pk=pk)
    _run(request, services.reject_step, step, user=request.user,
         comments=request.POST.get("comments", ""), success="Step rejected.")
    return redirect("web:approval_inbox")


# ---------------------------------------------------------------------------
# Inline formset factories
# ---------------------------------------------------------------------------
PRLineFS = inlineformset_factory(PurchaseRequisition, PurchaseRequisitionLine,
                                 form=PurchaseRequisitionLineForm, extra=3, can_delete=True)
POLineFS = inlineformset_factory(PurchaseOrder, PurchaseOrderLine,
                                 form=PurchaseOrderLineForm, extra=3, can_delete=True)
RFQLineFS = inlineformset_factory(RequestForQuotation, RFQLine,
                                  form=RFQLineForm, extra=3, can_delete=True)
QuotationLineFS = inlineformset_factory(SupplierQuotation, SupplierQuotationLine,
                                        form=SupplierQuotationLineForm, extra=1, can_delete=True)


def _style_formset(fs):
    for form in fs.forms:
        style_form(form)
    style_form(fs.empty_form)
    return fs


# ---------------------------------------------------------------------------
# Purchase Requisition
# ---------------------------------------------------------------------------
@login_required
def pr_list(request):
    prs = PurchaseRequisition.objects.select_related("project", "requested_by")
    return render(request, "web/pr_list.html", {"prs": prs,
                  "can_edit": request.user.can_manage_procurement})


@login_required
def pr_detail(request, pk):
    pr = get_object_or_404(
        PurchaseRequisition.objects.select_related("project", "requested_by", "approved_by")
        .prefetch_related("lines__material"), pk=pk)
    return render(request, "web/pr_detail.html", {"pr": pr,
                  "can_approve": request.user.can_approve,
                  "can_edit": request.user.can_manage_procurement})


@role_required("can_manage_procurement")
def pr_new(request):
    return _pr_form(request, PurchaseRequisition())


@role_required("can_manage_procurement")
def pr_edit(request, pk):
    pr = get_object_or_404(PurchaseRequisition, pk=pk)
    if pr.status != PurchaseRequisition.Status.DRAFT:
        messages.error(request, "Only draft requisitions can be edited.")
        return redirect("web:pr_detail", pk=pk)
    return _pr_form(request, pr)


def _pr_form(request, pr):
    form = PurchaseRequisitionForm(request.POST or None, instance=pr)
    style_form(form)
    formset = PRLineFS(request.POST or None, instance=pr)
    _style_formset(formset)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        is_new = pr.pk is None
        if is_new:
            pr = form.save(commit=False)
            pr.requested_by = request.user
            pr.save()
            formset.instance = pr
        else:
            form.save()
        formset.save()
        messages.success(request, f"Requisition {pr.number} saved.")
        return redirect("web:pr_detail", pk=pr.pk)
    return render(request, "web/document_form.html", {
        "title": "Purchase Requisition", "form": form, "formset": formset,
        "line_label": "Materials requested",
        "cancel_url": reverse("web:pr_list"),
    })


@role_required("can_manage_procurement")
def pr_submit(request, pk):
    _run(request, services.submit_requisition, get_object_or_404(PurchaseRequisition, pk=pk),
         success="Requisition submitted for approval.")
    return redirect("web:pr_detail", pk=pk)


@role_required("can_approve")
def pr_approve(request, pk):
    _run(request, services.approve_requisition, get_object_or_404(PurchaseRequisition, pk=pk),
         user=request.user, success="Requisition approved.")
    return redirect("web:pr_detail", pk=pk)


@role_required("can_approve")
def pr_reject(request, pk):
    _run(request, services.reject_requisition, get_object_or_404(PurchaseRequisition, pk=pk),
         user=request.user, reason=request.POST.get("reason", ""), success="Requisition rejected.")
    return redirect("web:pr_detail", pk=pk)


# ---------------------------------------------------------------------------
# Request for Quotation (RFQ)
# ---------------------------------------------------------------------------
@role_required("can_manage_procurement")
def pr_to_rfq(request, pk):
    """Convert an APPROVED requisition into a draft RFQ."""
    pr = get_object_or_404(PurchaseRequisition, pk=pk)
    try:
        rfq = services.create_rfq_from_requisition(pr, user=request.user)
        messages.success(request, f"RFQ {rfq.number} created from {pr.number}.")
        return redirect("web:rfq_detail", pk=rfq.pk)
    except services.TransitionError as exc:
        messages.error(request, str(exc))
        return redirect("web:pr_detail", pk=pk)


@login_required
def rfq_list(request):
    rfqs = RequestForQuotation.objects.select_related("project").prefetch_related("vendors")
    return render(request, "web/rfq_list.html", {"rfqs": rfqs,
                  "can_edit": request.user.can_manage_procurement})


@login_required
def rfq_detail(request, pk):
    rfq = get_object_or_404(
        RequestForQuotation.objects.select_related("project", "requisition", "created_by")
        .prefetch_related("lines__material", "vendors"), pk=pk)
    return render(request, "web/rfq_detail.html", {"rfq": rfq,
                  "can_edit": request.user.can_manage_procurement})


@role_required("can_manage_procurement")
def rfq_new(request):
    return _rfq_form(request, RequestForQuotation())


@role_required("can_manage_procurement")
def rfq_edit(request, pk):
    rfq = get_object_or_404(RequestForQuotation, pk=pk)
    if rfq.status != RequestForQuotation.Status.DRAFT:
        messages.error(request, "Only draft RFQs can be edited.")
        return redirect("web:rfq_detail", pk=pk)
    return _rfq_form(request, rfq)


def _rfq_form(request, rfq):
    form = RequestForQuotationForm(request.POST or None, instance=rfq)
    style_form(form)
    formset = RFQLineFS(request.POST or None, instance=rfq)
    _style_formset(formset)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        is_new = rfq.pk is None
        if is_new:
            rfq = form.save(commit=False)
            rfq.created_by = request.user
            rfq.save()
            form.save_m2m()
            formset.instance = rfq
        else:
            form.save()
        formset.save()
        messages.success(request, f"RFQ {rfq.number} saved.")
        return redirect("web:rfq_detail", pk=rfq.pk)
    return render(request, "web/document_form.html", {
        "title": "Request for Quotation", "form": form, "formset": formset,
        "line_label": "Materials to quote", "cancel_url": reverse("web:rfq_list"),
    })


@role_required("can_manage_procurement")
def rfq_send(request, pk):
    _run(request, services.send_rfq, get_object_or_404(RequestForQuotation, pk=pk),
         user=request.user, success="RFQ sent to the selected suppliers.")
    return redirect("web:rfq_detail", pk=pk)


@role_required("can_manage_procurement")
def rfq_close(request, pk):
    _run(request, services.close_rfq, get_object_or_404(RequestForQuotation, pk=pk),
         success="RFQ closed.")
    return redirect("web:rfq_detail", pk=pk)


@role_required("can_manage_procurement")
def rfq_cancel(request, pk):
    _run(request, services.cancel_rfq, get_object_or_404(RequestForQuotation, pk=pk),
         success="RFQ cancelled.")
    return redirect("web:rfq_detail", pk=pk)


# ---------------------------------------------------------------------------
# Supplier Quotations & comparison
# ---------------------------------------------------------------------------
@role_required("can_manage_procurement")
def quotation_new(request, rfq_pk):
    rfq = get_object_or_404(RequestForQuotation, pk=rfq_pk)
    initial = [{"material": ln.material_id, "quantity": ln.quantity} for ln in rfq.lines.all()]
    FS = inlineformset_factory(SupplierQuotation, SupplierQuotationLine,
                               form=SupplierQuotationLineForm,
                               extra=max(len(initial), 1), can_delete=True)
    form = SupplierQuotationForm(request.POST or None, rfq=rfq)
    style_form(form)
    quotation = SupplierQuotation(rfq=rfq)
    formset = FS(request.POST or None, instance=quotation,
                 initial=None if request.method == "POST" else initial)
    _style_formset(formset)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        quotation = form.save(commit=False)
        quotation.rfq = rfq
        quotation.created_by = request.user
        quotation.save()
        formset.instance = quotation
        formset.save()
        quotation.recalculate_totals()
        messages.success(request, f"Quotation {quotation.number} recorded.")
        return redirect("web:quotation_compare", rfq_pk=rfq.pk)
    return render(request, "web/document_form.html", {
        "title": f"Record Quotation — {rfq.number}", "form": form, "formset": formset,
        "line_label": "Quoted lines (qty, unit price, tax %)",
        "cancel_url": reverse("web:rfq_detail", args=[rfq.pk]),
    })


@login_required
def quotation_compare(request, rfq_pk):
    rfq = get_object_or_404(
        RequestForQuotation.objects.prefetch_related(
            "quotations__vendor", "quotations__lines__material", "lines__material"), pk=rfq_pk)
    quotations = list(rfq.quotations.all())
    # Build a per-material price matrix for easy side-by-side comparison.
    materials = {ln.material_id: ln.material for ln in rfq.lines.all()}
    matrix = []
    for mid, mat in materials.items():
        row = {"material": mat, "cells": []}
        for q in quotations:
            ql = next((qln for qln in q.lines.all() if qln.material_id == mid), None)
            row["cells"].append(ql)
        matrix.append(row)
    return render(request, "web/quotation_compare.html", {
        "rfq": rfq, "quotations": quotations, "matrix": matrix,
        "can_approve": request.user.can_approve,
        "can_edit": request.user.can_manage_procurement,
    })


@role_required("can_approve")
def quotation_select(request, pk):
    quotation = get_object_or_404(SupplierQuotation, pk=pk)
    try:
        po = services.select_quotation(quotation, user=request.user)
        messages.success(request, f"Quotation {quotation.number} selected — draft PO {po.number} created.")
        return redirect("web:po_detail", pk=po.pk)
    except services.TransitionError as exc:
        messages.error(request, str(exc))
        return redirect("web:quotation_compare", rfq_pk=quotation.rfq_id)


@role_required("can_manage_procurement")
def quotation_reject(request, pk):
    quotation = get_object_or_404(SupplierQuotation, pk=pk)
    _run(request, services.reject_quotation, quotation, success="Quotation rejected.")
    return redirect("web:quotation_compare", rfq_pk=quotation.rfq_id)


# ---------------------------------------------------------------------------
# Purchase Order
# ---------------------------------------------------------------------------
@login_required
def po_list(request):
    pos = PurchaseOrder.objects.select_related("vendor", "project")
    return render(request, "web/po_list.html", {"pos": pos,
                  "can_edit": request.user.can_manage_procurement})


@login_required
def po_detail(request, pk):
    po = get_object_or_404(
        PurchaseOrder.objects.select_related("vendor", "project", "created_by", "requisition")
        .prefetch_related("lines__material", "grns", "bills"), pk=pk)
    approval = services.open_approval_for(po)
    return render(request, "web/po_detail.html", {"po": po,
                  "can_approve": request.user.can_approve,
                  "can_edit": request.user.can_manage_procurement,
                  "can_bill": request.user.can_manage_bills,
                  "approval": approval,
                  "attachments": attachments_for(po),
                  "attachment_form": AttachmentForm(),
                  "needs_approval": services.po_approval_rules_apply(po),
                  "receivable": po.status in {PurchaseOrder.Status.ISSUED,
                                              PurchaseOrder.Status.PARTIALLY_RECEIVED}})


@role_required("can_manage_procurement")
def po_submit_approval(request, pk):
    _run(request, services.submit_po_for_approval, get_object_or_404(PurchaseOrder, pk=pk),
         user=request.user, success="Purchase order submitted for approval.")
    return redirect("web:po_detail", pk=pk)


@role_required("can_approve")
def po_reopen(request, pk):
    _run(request, services.reopen_purchase_order, get_object_or_404(PurchaseOrder, pk=pk),
         user=request.user, success="Purchase order re-opened for revision.")
    return redirect("web:po_detail", pk=pk)


@role_required("can_manage_procurement")
def po_email(request, pk):
    _run(request, services.email_purchase_order, get_object_or_404(PurchaseOrder, pk=pk),
         success="Purchase order emailed to the vendor.")
    return redirect("web:po_detail", pk=pk)


@login_required
def po_pdf(request, pk):
    po = get_object_or_404(
        PurchaseOrder.objects.select_related("vendor", "project")
        .prefetch_related("lines__material"), pk=pk)
    return _render_pdf(request, "web/pdf/po_pdf.html", {
        "po": po, "doc_kind": "Purchase Order", "doc_number": po.number,
        "status_label": po.get_status_display(),
        "status_color": _po_status_color(po.status),
    }, f"{po.number}.pdf")


def _po_status_color(status):
    from web.templatetags.web_extras import status_color
    return status_color(status)


@login_required
def pr_pdf(request, pk):
    pr = get_object_or_404(
        PurchaseRequisition.objects.select_related("project", "requested_by", "approved_by")
        .prefetch_related("lines__material"), pk=pk)
    return _render_pdf(request, "web/pdf/pr_pdf.html", {
        "pr": pr, "doc_kind": "Requisition", "doc_number": pr.number,
        "status_label": pr.get_status_display(),
        "status_color": _po_status_color(pr.status),
    }, f"{pr.number}.pdf")


@role_required("can_manage_procurement")
def po_new(request):
    po = PurchaseOrder()
    initial_lines = None
    # Optional prefill from an approved requisition.
    req_id = request.GET.get("requisition")
    if req_id and request.method == "GET":
        pr = get_object_or_404(PurchaseRequisition, pk=req_id)
        po.project = pr.project
        po.requisition = pr
        initial_lines = [{"material": ln.material_id, "quantity": ln.quantity}
                         for ln in pr.lines.all()]
    return _po_form(request, po, initial_lines)


@role_required("can_manage_procurement")
def po_edit(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    if po.status != PurchaseOrder.Status.DRAFT:
        messages.error(request, "Only draft purchase orders can be edited.")
        return redirect("web:po_detail", pk=pk)
    return _po_form(request, po)


def _po_form(request, po, initial_lines=None):
    form = PurchaseOrderForm(request.POST or None, instance=po)
    style_form(form)
    fs_kwargs = {"instance": po}
    if initial_lines is not None:
        FS = inlineformset_factory(PurchaseOrder, PurchaseOrderLine,
                                   form=PurchaseOrderLineForm,
                                   extra=len(initial_lines) + 1, can_delete=True)
        formset = FS(request.POST or None, initial=initial_lines, **fs_kwargs)
    else:
        formset = POLineFS(request.POST or None, **fs_kwargs)
    _style_formset(formset)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        is_new = po.pk is None
        if is_new:
            po = form.save(commit=False)
            po.created_by = request.user
            po.save()
            formset.instance = po
        else:
            form.save()
        formset.save()
        po.recalculate_totals()
        messages.success(request, f"Purchase order {po.number} saved.")
        return redirect("web:po_detail", pk=po.pk)
    return render(request, "web/document_form.html", {
        "title": "Purchase Order", "form": form, "formset": formset,
        "line_label": "Order lines (qty, unit price, tax %)",
        "cancel_url": reverse("web:po_list"),
    })


@role_required("can_approve")
def po_issue(request, pk):
    _run(request, services.issue_purchase_order, get_object_or_404(PurchaseOrder, pk=pk),
         user=request.user, success="Purchase order issued to vendor.")
    return redirect("web:po_detail", pk=pk)


@role_required("can_approve")
def po_cancel(request, pk):
    _run(request, services.cancel_purchase_order, get_object_or_404(PurchaseOrder, pk=pk),
         success="Purchase order cancelled.")
    return redirect("web:po_detail", pk=pk)


@role_required("can_approve")
def po_close(request, pk):
    _run(request, services.close_purchase_order, get_object_or_404(PurchaseOrder, pk=pk),
         success="Purchase order closed.")
    return redirect("web:po_detail", pk=pk)


# ---------------------------------------------------------------------------
# Goods Receipt Note (created scoped to a PO)
# ---------------------------------------------------------------------------
@login_required
def grn_list(request):
    grns = GoodsReceiptNote.objects.select_related("purchase_order", "received_by")
    issuable = PurchaseOrder.objects.filter(
        status__in=[PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.PARTIALLY_RECEIVED])
    return render(request, "web/grn_list.html", {"grns": grns, "issuable_pos": issuable,
                  "can_edit": request.user.can_manage_procurement})


@login_required
def grn_detail(request, pk):
    grn = get_object_or_404(
        GoodsReceiptNote.objects.select_related("purchase_order", "received_by")
        .prefetch_related("lines__po_line__material"), pk=pk)
    return render(request, "web/grn_detail.html", {"grn": grn,
                  "can_edit": request.user.can_manage_procurement,
                  "attachments": attachments_for(grn),
                  "attachment_form": AttachmentForm(initial={"kind": "DELIVERY_NOTE"})})


@role_required("can_manage_procurement")
def grn_new(request, po_pk):
    po = get_object_or_404(PurchaseOrder, pk=po_pk)
    if po.status not in {PurchaseOrder.Status.ISSUED, PurchaseOrder.Status.PARTIALLY_RECEIVED}:
        messages.error(request, "Goods can only be received against an issued PO.")
        return redirect("web:po_detail", pk=po_pk)

    pending_lines = [ln for ln in po.lines.all() if ln.pending_quantity > 0]
    initial = [{"po_line": ln.pk, "received_quantity": ln.pending_quantity,
                "accepted_quantity": ln.pending_quantity} for ln in pending_lines]
    FS = inlineformset_factory(GoodsReceiptNote, GRNLine, form=GRNLineForm,
                               extra=max(len(initial), 1), can_delete=True)

    form = GoodsReceiptNoteForm(request.POST or None)
    style_form(form)
    grn = GoodsReceiptNote(purchase_order=po)
    formset = FS(request.POST or None, instance=grn,
                 initial=None if request.method == "POST" else initial)
    # Restrict po_line choices to this PO's lines.
    po_line_qs = po.lines.select_related("material")
    for f in formset.forms:
        f.fields["po_line"].queryset = po_line_qs
    formset.empty_form.fields["po_line"].queryset = po_line_qs
    _style_formset(formset)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        grn = form.save(commit=False)
        grn.purchase_order = po
        grn.received_by = request.user
        grn.save()
        formset.instance = grn
        formset.save()
        messages.success(request, f"GRN {grn.number} created (draft).")
        return redirect("web:grn_detail", pk=grn.pk)
    return render(request, "web/document_form.html", {
        "title": f"Goods Receipt — against {po.number}", "form": form, "formset": formset,
        "line_label": "Received / accepted quantities", "cancel_url": reverse("web:po_detail", args=[po.pk]),
    })


@role_required("can_manage_procurement")
def grn_confirm(request, pk):
    _run(request, services.confirm_grn, get_object_or_404(GoodsReceiptNote, pk=pk),
         success="GRN confirmed; quantities posted to the PO.")
    return redirect("web:grn_detail", pk=pk)


@role_required("can_manage_procurement")
def grn_cancel(request, pk):
    _run(request, services.cancel_grn, get_object_or_404(GoodsReceiptNote, pk=pk),
         success="GRN cancelled.")
    return redirect("web:grn_detail", pk=pk)


# ---------------------------------------------------------------------------
# Inventory — Stock on-hand + ledger
# ---------------------------------------------------------------------------
@login_required
def stock_list(request):
    items = StockItem.objects.select_related("material", "project")
    project_id = request.GET.get("project")
    if project_id:
        items = items.filter(project_id=project_id)
    return render(request, "web/stock_list.html", {
        "items": items, "projects": Project.objects.all(),
        "selected_project": project_id})


@login_required
def stock_ledger(request):
    entries = StockLedgerEntry.objects.select_related("material", "project")[:300]
    return render(request, "web/stock_ledger.html", {"entries": entries})


# ---------------------------------------------------------------------------
# Quality Inspection
# ---------------------------------------------------------------------------
QCItemFS = inlineformset_factory(QualityInspection, QCChecklistItem,
                                 form=QCChecklistItemForm, extra=4, can_delete=True)

_DEFAULT_QC_CHECKS = [
    "Quantity matches challan", "No transit / physical damage",
    "Correct specification / grade", "Packaging & labelling intact",
]


@role_required("can_manage_procurement")
def inspection_new(request, grn_pk):
    grn = get_object_or_404(GoodsReceiptNote, pk=grn_pk)
    inspection = QualityInspection(grn=grn)
    form = QualityInspectionForm(request.POST or None, instance=inspection)
    style_form(form)
    initial = [{"description": d} for d in _DEFAULT_QC_CHECKS]
    FS = inlineformset_factory(QualityInspection, QCChecklistItem,
                               form=QCChecklistItemForm,
                               extra=len(initial) + 1, can_delete=True)
    formset = FS(request.POST or None, instance=inspection,
                 initial=None if request.method == "POST" else initial)
    _style_formset(formset)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        inspection = form.save(commit=False)
        inspection.grn = grn
        inspection.save()
        formset.instance = inspection
        formset.save()
        messages.success(request, f"Inspection {inspection.number} created.")
        return redirect("web:inspection_detail", pk=inspection.pk)
    return render(request, "web/document_form.html", {
        "title": f"Quality Inspection — {grn.number}", "form": form, "formset": formset,
        "line_label": "Checklist", "cancel_url": reverse("web:grn_detail", args=[grn.pk]),
    })


@login_required
def inspection_detail(request, pk):
    inspection = get_object_or_404(
        QualityInspection.objects.select_related("grn", "inspected_by")
        .prefetch_related("items"), pk=pk)
    return render(request, "web/inspection_detail.html", {
        "inspection": inspection,
        "can_edit": request.user.can_manage_procurement,
        "attachments": attachments_for(inspection),
        "attachment_form": AttachmentForm(initial={"kind": "INSPECTION"}),
    })


@role_required("can_manage_procurement")
def inspection_submit(request, pk):
    _run(request, services.submit_inspection, get_object_or_404(QualityInspection, pk=pk),
         user=request.user, success="Inspection completed.")
    return redirect("web:inspection_detail", pk=pk)


# ---------------------------------------------------------------------------
# Vendor Bill (created scoped to a PO) — 3-way match
# ---------------------------------------------------------------------------
@login_required
def bill_list(request):
    bills = VendorBill.objects.select_related("vendor", "purchase_order")
    billable = PurchaseOrder.objects.exclude(
        status__in=[PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.CANCELLED])
    return render(request, "web/bill_list.html", {"bills": bills, "billable_pos": billable,
                  "can_edit": request.user.can_manage_bills})


@login_required
def bill_detail(request, pk):
    bill = get_object_or_404(
        VendorBill.objects.select_related("vendor", "purchase_order", "created_by")
        .prefetch_related("lines__po_line__material", "payments", "schedules"), pk=pk)
    return render(request, "web/bill_detail.html", {"bill": bill,
                  "can_edit": request.user.can_manage_bills,
                  "attachments": attachments_for(bill),
                  "attachment_form": AttachmentForm(initial={"kind": "INVOICE"})})


@role_required("can_manage_bills")
def bill_new(request, po_pk):
    po = get_object_or_404(PurchaseOrder, pk=po_pk)
    po_lines = list(po.lines.select_related("material"))
    initial = [{"po_line": ln.pk, "quantity": ln.received_quantity or ln.quantity,
                "unit_price": ln.unit_price, "tax_rate": ln.tax_rate} for ln in po_lines]
    FS = inlineformset_factory(VendorBill, VendorBillLine, form=VendorBillLineForm,
                               extra=max(len(initial), 1), can_delete=True)

    form = VendorBillForm(request.POST or None)
    style_form(form)
    bill = VendorBill(purchase_order=po, vendor=po.vendor)
    formset = FS(request.POST or None, instance=bill,
                 initial=None if request.method == "POST" else initial)
    po_line_qs = po.lines.select_related("material")
    for f in formset.forms:
        f.fields["po_line"].queryset = po_line_qs
    formset.empty_form.fields["po_line"].queryset = po_line_qs
    _style_formset(formset)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        bill = form.save(commit=False)
        bill.purchase_order = po
        bill.vendor = po.vendor
        bill.created_by = request.user
        bill.save()
        formset.instance = bill
        formset.save()
        bill.recalculate_totals()
        messages.success(request, f"Bill {bill.number} created (draft).")
        return redirect("web:bill_detail", pk=bill.pk)
    return render(request, "web/document_form.html", {
        "title": f"Vendor Bill — against {po.number}", "form": form, "formset": formset,
        "line_label": "Billed lines (qty, unit price, tax %)", "cancel_url": reverse("web:po_detail", args=[po.pk]),
    })


@role_required("can_manage_bills")
def bill_match(request, pk):
    services.run_three_way_match(get_object_or_404(VendorBill, pk=pk))
    messages.success(request, "3-way match run — see the result below.")
    return redirect("web:bill_detail", pk=pk)


@role_required("can_manage_bills")
def bill_approve(request, pk):
    _run(request, services.approve_bill, get_object_or_404(VendorBill, pk=pk),
         success="Bill approved for payment.")
    return redirect("web:bill_detail", pk=pk)


@role_required("can_manage_bills")
def bill_mark_paid(request, pk):
    _run(request, services.mark_bill_paid, get_object_or_404(VendorBill, pk=pk),
         success="Bill marked as paid.")
    return redirect("web:bill_detail", pk=pk)


# ---------------------------------------------------------------------------
# Supplier Payments
# ---------------------------------------------------------------------------
@login_required
def payment_list(request):
    payments = Payment.objects.select_related("vendor", "bill")
    schedules = PaymentSchedule.objects.select_related("vendor", "bill").filter(
        status=PaymentSchedule.Status.PENDING)
    return render(request, "web/payment_list.html", {
        "payments": payments, "schedules": schedules,
        "can_edit": request.user.can_manage_bills})


@role_required("can_manage_bills")
def payment_new(request):
    payment = Payment()
    bill_id = request.GET.get("bill")
    if bill_id and request.method == "GET":
        bill = get_object_or_404(VendorBill, pk=bill_id)
        payment.bill = bill
        payment.vendor = bill.vendor
        payment.purchase_order = bill.purchase_order
        payment.amount = bill.outstanding
        payment.payment_type = Payment.Type.AGAINST_BILL
    form = PaymentForm(request.POST or None, instance=payment)
    style_form(form)
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.created_by = request.user
        payment.save()
        messages.success(request, f"Payment {payment.number} recorded (pending).")
        return redirect("web:payment_list")
    return render(request, "web/master_form.html", {"title": "Record Payment", "form": form})


@role_required("can_manage_bills")
def payment_post(request, pk):
    _run(request, services.post_payment, get_object_or_404(Payment, pk=pk),
         success="Payment posted.")
    return redirect("web:payment_list")


@role_required("can_manage_bills")
def payment_cancel(request, pk):
    _run(request, services.cancel_payment, get_object_or_404(Payment, pk=pk),
         success="Payment cancelled.")
    return redirect("web:payment_list")


@role_required("can_manage_bills")
def schedule_new(request):
    schedule = PaymentSchedule()
    bill_id = request.GET.get("bill")
    if bill_id and request.method == "GET":
        bill = get_object_or_404(VendorBill, pk=bill_id)
        schedule.bill = bill
        schedule.vendor = bill.vendor
        schedule.amount = bill.outstanding
    form = PaymentScheduleForm(request.POST or None, instance=schedule)
    style_form(form)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Payment schedule added.")
        return redirect("web:payment_list")
    return render(request, "web/master_form.html", {"title": "New Payment Schedule", "form": form})


# ---------------------------------------------------------------------------
# Purchase Returns
# ---------------------------------------------------------------------------
@login_required
def return_list(request):
    returns = PurchaseReturn.objects.select_related("purchase_order", "vendor")
    return render(request, "web/return_list.html", {"returns": returns,
                  "can_edit": request.user.can_manage_procurement})


@login_required
def return_detail(request, pk):
    ret = get_object_or_404(
        PurchaseReturn.objects.select_related("purchase_order", "vendor", "created_by")
        .prefetch_related("lines__po_line__material"), pk=pk)
    return render(request, "web/return_detail.html", {"ret": ret,
                  "can_edit": request.user.can_manage_procurement})


@role_required("can_manage_procurement")
def return_new(request, po_pk):
    po = get_object_or_404(PurchaseOrder, pk=po_pk)
    received_lines = [ln for ln in po.lines.select_related("material") if ln.received_quantity > 0]
    initial = [{"po_line": ln.pk, "quantity": ln.received_quantity} for ln in received_lines]
    FS = inlineformset_factory(PurchaseReturn, PurchaseReturnLine,
                               form=PurchaseReturnLineForm,
                               extra=max(len(initial), 1), can_delete=True)
    form = PurchaseReturnForm(request.POST or None)
    style_form(form)
    ret = PurchaseReturn(purchase_order=po, vendor=po.vendor)
    formset = FS(request.POST or None, instance=ret,
                 initial=None if request.method == "POST" else initial)
    po_line_qs = po.lines.select_related("material")
    for f in formset.forms:
        f.fields["po_line"].queryset = po_line_qs
    formset.empty_form.fields["po_line"].queryset = po_line_qs
    _style_formset(formset)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        ret = form.save(commit=False)
        ret.purchase_order = po
        ret.vendor = po.vendor
        ret.created_by = request.user
        ret.save()
        formset.instance = ret
        formset.save()
        messages.success(request, f"Return {ret.number} created (draft).")
        return redirect("web:return_detail", pk=ret.pk)
    return render(request, "web/document_form.html", {
        "title": f"Purchase Return — against {po.number}", "form": form, "formset": formset,
        "line_label": "Return lines (qty)", "cancel_url": reverse("web:po_detail", args=[po.pk]),
    })


@role_required("can_manage_procurement")
def return_confirm(request, pk):
    _run(request, services.confirm_return, get_object_or_404(PurchaseReturn, pk=pk),
         success="Return confirmed; stock and PO quantities reversed.")
    return redirect("web:return_detail", pk=pk)


@role_required("can_manage_procurement")
def return_cancel(request, pk):
    _run(request, services.cancel_return, get_object_or_404(PurchaseReturn, pk=pk),
         success="Return cancelled.")
    return redirect("web:return_detail", pk=pk)


# ---------------------------------------------------------------------------
# Purchase Contracts
# ---------------------------------------------------------------------------
ContractLineFS = inlineformset_factory(PurchaseContract, ContractLine,
                                       form=ContractLineForm, extra=3, can_delete=True)


@login_required
def contract_list(request):
    contracts = PurchaseContract.objects.select_related("vendor")
    return render(request, "web/contract_list.html", {"contracts": contracts,
                  "can_edit": request.user.can_manage_procurement})


@login_required
def contract_detail(request, pk):
    contract = get_object_or_404(
        PurchaseContract.objects.select_related("vendor", "created_by")
        .prefetch_related("lines__material", "purchase_orders"), pk=pk)
    return render(request, "web/contract_detail.html", {"contract": contract,
                  "can_edit": request.user.can_manage_procurement,
                  "can_approve": request.user.can_approve})


@role_required("can_manage_procurement")
def contract_new(request):
    return _contract_form(request, PurchaseContract())


@role_required("can_manage_procurement")
def contract_edit(request, pk):
    contract = get_object_or_404(PurchaseContract, pk=pk)
    if contract.status not in {PurchaseContract.Status.DRAFT, PurchaseContract.Status.ACTIVE}:
        messages.error(request, "Only draft or active contracts can be edited.")
        return redirect("web:contract_detail", pk=pk)
    return _contract_form(request, contract)


def _contract_form(request, contract):
    form = PurchaseContractForm(request.POST or None, instance=contract)
    style_form(form)
    formset = ContractLineFS(request.POST or None, instance=contract)
    _style_formset(formset)
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        is_new = contract.pk is None
        if is_new:
            contract = form.save(commit=False)
            contract.created_by = request.user
            contract.save()
            formset.instance = contract
        else:
            form.save()
        formset.save()
        messages.success(request, f"Contract {contract.number} saved.")
        return redirect("web:contract_detail", pk=contract.pk)
    return render(request, "web/document_form.html", {
        "title": "Purchase Contract", "form": form, "formset": formset,
        "line_label": "Contract pricing (material, unit price, tax %)",
        "cancel_url": reverse("web:contract_list"),
    })


@role_required("can_approve")
def contract_activate(request, pk):
    _run(request, services.activate_contract, get_object_or_404(PurchaseContract, pk=pk),
         success="Contract activated.")
    return redirect("web:contract_detail", pk=pk)


@role_required("can_approve")
def contract_terminate(request, pk):
    _run(request, services.terminate_contract, get_object_or_404(PurchaseContract, pk=pk),
         success="Contract terminated.")
    return redirect("web:contract_detail", pk=pk)


@role_required("can_approve")
def contract_renew(request, pk):
    contract = get_object_or_404(PurchaseContract, pk=pk)
    start = request.POST.get("start_date") or contract.end_date
    end = request.POST.get("end_date")
    if not end:
        messages.error(request, "Provide a new end date to renew.")
        return redirect("web:contract_detail", pk=pk)
    try:
        new = services.renew_contract(contract, start_date=start, end_date=end, user=request.user)
        messages.success(request, f"Contract renewed as {new.number}.")
        return redirect("web:contract_detail", pk=new.pk)
    except services.TransitionError as exc:
        messages.error(request, str(exc))
        return redirect("web:contract_detail", pk=pk)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@login_required
def reports_index(request):
    items = [{"slug": slug, "title": spec[0]} for slug, spec in reports.REPORTS.items()]
    return render(request, "web/reports_index.html", {
        "items": items, "vendors": Vendor.objects.all()})


@login_required
def report_view(request, slug):
    spec = reports.REPORTS.get(slug)
    if not spec:
        messages.error(request, "Unknown report.")
        return redirect("web:reports_index")
    title, fn, columns = spec
    rows = fn()
    return render(request, "web/report_table.html", {
        "title": title, "columns": columns, "rows": rows})


@login_required
def supplier_ledger_report(request):
    vendor_id = request.GET.get("vendor")
    vendor = get_object_or_404(Vendor, pk=vendor_id) if vendor_id else None
    rows = reports.supplier_ledger(vendor) if vendor else []
    return render(request, "web/report_ledger.html", {
        "vendor": vendor, "vendors": Vendor.objects.all(), "rows": rows})


# ---------------------------------------------------------------------------
# Notifications + Audit history
# ---------------------------------------------------------------------------
@login_required
def notification_list(request):
    notes = services.notifications_for(request.user)[:100]
    return render(request, "web/notification_list.html", {"notes": notes})


@login_required
def notification_read(request, pk):
    note = services.notifications_for(request.user).filter(pk=pk).first()
    if note:
        note.is_read = True
        note.save(update_fields=["is_read", "updated_at"])
        if note.url:
            return redirect(note.url)
    return redirect("web:notification_list")


@login_required
def notifications_read_all(request):
    services.notifications_for(request.user).filter(is_read=False).update(is_read=True)
    messages.info(request, "All notifications marked read.")
    return redirect("web:notification_list")


@login_required
def audit_history(request, model, object_id):
    ct = get_object_or_404(ContentType, model=model, app_label="procurement")
    logs = AuditLog.objects.filter(content_type=ct, object_id=object_id).select_related("actor")
    obj = ct.model_class().objects.filter(pk=object_id).first()
    return render(request, "web/audit_history.html", {"logs": logs, "obj": obj})
