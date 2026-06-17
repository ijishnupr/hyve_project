"""Server-rendered views for the procurement frontend.

Thin layer over ``procurement.services`` — all state transitions delegate to the
service functions (the same ones the API uses), so the business rules live in one
place. Permissions mirror the DRF permission classes via role predicates on User.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import Count
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from procurement import services
from procurement.models import (
    GoodsReceiptNote,
    GRNLine,
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

from .forms import (
    GoodsReceiptNoteForm,
    GRNLineForm,
    MaterialCategoryForm,
    MaterialForm,
    ProjectForm,
    PurchaseOrderForm,
    PurchaseOrderLineForm,
    PurchaseRequisitionForm,
    PurchaseRequisitionLineForm,
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
# Dashboard
# ---------------------------------------------------------------------------
def _status_counts(model):
    return {
        row["status"]: row["n"]
        for row in model.objects.values("status").annotate(n=Count("id"))
    }


@login_required
def dashboard(request):
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
        "pr_status": _status_counts(PurchaseRequisition),
        "po_status": _status_counts(PurchaseOrder),
        "bill_status": _status_counts(VendorBill),
        "recent_prs": PurchaseRequisition.objects.select_related("project")[:5],
        "recent_pos": PurchaseOrder.objects.select_related("vendor", "project")[:5],
        "recent_bills": VendorBill.objects.select_related("vendor")[:5],
    }
    return render(request, "web/dashboard.html", ctx)


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
    return _master_list(
        request, title="Vendors", queryset=Vendor.objects.all(),
        headers=["Code", "Name", "GSTIN", "Contact", "Terms (days)", "Active"],
        row_fn=lambda o: [o.code, o.name, o.gstin, o.contact_person, o.payment_terms_days,
                          "Yes" if o.is_active else "No"],
        new_url=reverse("web:vendor_new"), edit_name="web:vendor_edit",
        can_edit=request.user.can_manage_procurement,
    )


@role_required("can_manage_procurement")
def vendor_new(request):
    return _master_form(request, title="New Vendor", form_class=VendorForm, list_name="web:vendor_list")


@role_required("can_manage_procurement")
def vendor_edit(request, pk):
    return _master_form(request, title="Edit Vendor", form_class=VendorForm,
                        instance=get_object_or_404(Vendor, pk=pk), list_name="web:vendor_list")


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
# Inline formset factories
# ---------------------------------------------------------------------------
PRLineFS = inlineformset_factory(PurchaseRequisition, PurchaseRequisitionLine,
                                 form=PurchaseRequisitionLineForm, extra=3, can_delete=True)
POLineFS = inlineformset_factory(PurchaseOrder, PurchaseOrderLine,
                                 form=PurchaseOrderLineForm, extra=3, can_delete=True)


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
    return render(request, "web/po_detail.html", {"po": po,
                  "can_approve": request.user.can_approve,
                  "can_edit": request.user.can_manage_procurement,
                  "can_bill": request.user.can_manage_bills,
                  "receivable": po.status in {PurchaseOrder.Status.ISSUED,
                                              PurchaseOrder.Status.PARTIALLY_RECEIVED}})


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
                  "can_edit": request.user.can_manage_procurement})


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
        .prefetch_related("lines__po_line__material"), pk=pk)
    return render(request, "web/bill_detail.html", {"bill": bill,
                  "can_edit": request.user.can_manage_bills})


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
