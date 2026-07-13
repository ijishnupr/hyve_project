"""
Business logic for procurement state transitions.

Kept out of views/serializers so the rules are testable in isolation and
reused by the API, the admin and any background tasks.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from accounts.models import Role

from .models import (
    ApprovalDocumentType,
    ApprovalRequest,
    ApprovalRule,
    ApprovalStep,
    AuditLog,
    ContractLine,
    GoodsReceiptNote,
    Notification,
    Payment,
    PurchaseContract,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderRevision,
    PurchaseRequisition,
    PurchaseReturn,
    QCChecklistItem,
    QualityInspection,
    RequestForQuotation,
    RFQLine,
    StockItem,
    StockLedgerEntry,
    SupplierQuotation,
    VendorBill,
)


class TransitionError(Exception):
    """Raised when a requested state transition is not allowed."""


# ---------------------------------------------------------------------------
# Audit trail + notifications (cross-cutting helpers)
# ---------------------------------------------------------------------------
def log_action(document, *, action: str, user=None, from_status: str = "",
               to_status: str = "", note: str = "") -> AuditLog:
    """Append an immutable audit-trail entry for a document action."""
    from django.contrib.contenttypes.models import ContentType as _CT
    ct = _CT.objects.get_for_model(type(document))
    return AuditLog.objects.create(
        content_type=ct, object_id=document.pk, document_label=str(document),
        action=action, from_status=from_status, to_status=to_status,
        note=note, actor=user,
    )


def notify(*, message: str, kind: str = Notification.Kind.GENERAL, url: str = "",
           recipient=None, recipient_role: str = "") -> Notification:
    """Create an in-app notification for a user or a whole role."""
    return Notification.objects.create(
        recipient=recipient, recipient_role=recipient_role or "",
        kind=kind, message=message, url=url,
    )


def notifications_for(user):
    """Notifications addressed to a user directly or to their role."""
    from django.db.models import Q
    return Notification.objects.filter(
        Q(recipient=user) | Q(recipient__isnull=True, recipient_role=user.role)
        | Q(recipient__isnull=True, recipient_role="")
    )


# ---------------------------------------------------------------------------
# Approval workflow
# ---------------------------------------------------------------------------
def _user_can_act(user, role_required: str) -> bool:
    return bool(user and (user.role == role_required or user.role == Role.ADMIN))


def open_approval_for(document) -> ApprovalRequest | None:
    """Return the latest PENDING/APPROVED approval request for a document, if any."""
    ct = ContentType.objects.get_for_model(type(document))
    return (
        ApprovalRequest.objects.filter(content_type=ct, object_id=document.pk)
        .order_by("-created_at")
        .first()
    )


def document_is_approved(document) -> bool:
    req = open_approval_for(document)
    return bool(req and req.status == ApprovalRequest.Status.APPROVED)


@transaction.atomic
def start_approval(document, *, document_type: str, amount: Decimal) -> ApprovalRequest | None:
    """Build an ApprovalRequest with one step per matching matrix rule.

    Returns ``None`` when no active rule matches (i.e. no approval is required).
    Rejects a duplicate while one is already pending.
    """
    existing = open_approval_for(document)
    if existing and existing.status == ApprovalRequest.Status.PENDING:
        raise TransitionError("An approval is already pending for this document.")

    rules = [
        r for r in ApprovalRule.objects.filter(
            document_type=document_type, is_active=True).order_by("level")
        if r.matches_amount(amount)
    ]
    if not rules:
        return None

    # One step per distinct level (lowest min_amount rule wins per level).
    by_level: dict[int, ApprovalRule] = {}
    for r in rules:
        by_level.setdefault(r.level, r)

    ct = ContentType.objects.get_for_model(type(document))
    request = ApprovalRequest.objects.create(
        content_type=ct, object_id=document.pk,
        document_type=document_type, amount=amount,
        current_level=min(by_level),
    )
    now = timezone.now()
    for level in sorted(by_level):
        rule = by_level[level]
        due = now + timedelta(hours=rule.escalate_after_hours) if rule.escalate_after_hours else None
        ApprovalStep.objects.create(
            request=request, level=level, role_required=rule.role_required, due_at=due,
        )
    return request


@transaction.atomic
def approve_step(step: ApprovalStep, *, user, comments: str = "") -> ApprovalStep:
    request = step.request
    if request.status != ApprovalRequest.Status.PENDING:
        raise TransitionError("This approval is no longer pending.")
    if step.status != ApprovalStep.Status.PENDING:
        raise TransitionError("This step has already been actioned.")
    if step.level != request.current_level:
        raise TransitionError("An earlier approval level is still pending.")
    if not _user_can_act(user, step.role_required):
        raise TransitionError("You do not hold the role required for this approval level.")

    step.status = ApprovalStep.Status.APPROVED
    step.acted_by = user
    step.acted_at = timezone.now()
    step.comments = comments
    step.save(update_fields=["status", "acted_by", "acted_at", "comments", "updated_at"])

    remaining = request.steps.filter(status=ApprovalStep.Status.PENDING).order_by("level")
    if remaining.exists():
        request.current_level = remaining.first().level
        request.save(update_fields=["current_level", "updated_at"])
    else:
        request.status = ApprovalRequest.Status.APPROVED
        request.save(update_fields=["status", "updated_at"])
    return step


@transaction.atomic
def reject_step(step: ApprovalStep, *, user, comments: str = "") -> ApprovalStep:
    request = step.request
    if request.status != ApprovalRequest.Status.PENDING:
        raise TransitionError("This approval is no longer pending.")
    if step.status != ApprovalStep.Status.PENDING:
        raise TransitionError("This step has already been actioned.")
    if not _user_can_act(user, step.role_required):
        raise TransitionError("You do not hold the role required for this approval level.")

    step.status = ApprovalStep.Status.REJECTED
    step.acted_by = user
    step.acted_at = timezone.now()
    step.comments = comments
    step.save(update_fields=["status", "acted_by", "acted_at", "comments", "updated_at"])
    request.status = ApprovalRequest.Status.REJECTED
    request.save(update_fields=["status", "updated_at"])
    return step


def pending_steps_for_user(user):
    """Approval steps currently awaiting *this* user's role at the active level."""
    roles = {Role.ADMIN, user.role} if user else set()
    steps = (
        ApprovalStep.objects.select_related("request")
        .filter(status=ApprovalStep.Status.PENDING,
                request__status=ApprovalRequest.Status.PENDING)
    )
    return [s for s in steps if s.level == s.request.current_level
            and (s.role_required in roles or user.role == Role.ADMIN)]


# ---------------------------------------------------------------------------
# Purchase Requisition
# ---------------------------------------------------------------------------
def submit_requisition(pr: PurchaseRequisition) -> PurchaseRequisition:
    if pr.status != PurchaseRequisition.Status.DRAFT:
        raise TransitionError("Only draft requisitions can be submitted.")
    if not pr.lines.exists():
        raise TransitionError("Cannot submit a requisition with no line items.")
    pr.status = PurchaseRequisition.Status.SUBMITTED
    pr.save(update_fields=["status", "updated_at"])
    log_action(pr, action="Submitted for approval", from_status="DRAFT", to_status="SUBMITTED")
    notify(message=f"Requisition {pr.number} awaits approval",
           kind=Notification.Kind.APPROVAL, recipient_role="PROCUREMENT_MANAGER",
           url=f"/requisitions/{pr.pk}/")
    return pr


def approve_requisition(pr: PurchaseRequisition, *, user) -> PurchaseRequisition:
    if pr.status != PurchaseRequisition.Status.SUBMITTED:
        raise TransitionError("Only submitted requisitions can be approved.")
    pr.status = PurchaseRequisition.Status.APPROVED
    pr.approved_by = user
    pr.approved_at = timezone.now()
    pr.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    log_action(pr, action="Approved", user=user, from_status="SUBMITTED", to_status="APPROVED")
    return pr


def reject_requisition(pr: PurchaseRequisition, *, user, reason: str) -> PurchaseRequisition:
    if pr.status != PurchaseRequisition.Status.SUBMITTED:
        raise TransitionError("Only submitted requisitions can be rejected.")
    pr.status = PurchaseRequisition.Status.REJECTED
    pr.approved_by = user
    pr.approved_at = timezone.now()
    pr.rejection_reason = reason
    pr.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "updated_at",
        ]
    )
    return pr


# ---------------------------------------------------------------------------
# Request for Quotation (RFQ)
# ---------------------------------------------------------------------------
@transaction.atomic
def create_rfq_from_requisition(pr: PurchaseRequisition, *, user) -> RequestForQuotation:
    """Spin up a draft RFQ pre-filled from an APPROVED requisition's lines."""
    if pr.status != PurchaseRequisition.Status.APPROVED:
        raise TransitionError("Only approved requisitions can be converted to an RFQ.")
    rfq = RequestForQuotation.objects.create(
        project=pr.project, requisition=pr, created_by=user
    )
    RFQLine.objects.bulk_create(
        [RFQLine(rfq=rfq, material=ln.material, quantity=ln.quantity, remarks=ln.remarks)
         for ln in pr.lines.all()]
    )
    return rfq


def send_rfq(rfq: RequestForQuotation, *, user=None) -> RequestForQuotation:
    if rfq.status != RequestForQuotation.Status.DRAFT:
        raise TransitionError("Only draft RFQs can be sent.")
    if not rfq.lines.exists():
        raise TransitionError("Cannot send an RFQ with no line items.")
    if not rfq.vendors.exists():
        raise TransitionError("Add at least one supplier before sending the RFQ.")
    rfq.status = RequestForQuotation.Status.SENT
    rfq.sent_at = timezone.now()
    rfq.save(update_fields=["status", "sent_at", "updated_at"])
    log_action(rfq, action="Sent to suppliers", user=user, to_status="SENT")
    notify(message=f"RFQ {rfq.number} sent to {rfq.vendors.count()} supplier(s)",
           kind=Notification.Kind.RFQ, url=f"/rfqs/{rfq.pk}/")
    return rfq


def close_rfq(rfq: RequestForQuotation) -> RequestForQuotation:
    if rfq.status != RequestForQuotation.Status.SENT:
        raise TransitionError("Only sent RFQs can be closed.")
    rfq.status = RequestForQuotation.Status.CLOSED
    rfq.save(update_fields=["status", "updated_at"])
    return rfq


def cancel_rfq(rfq: RequestForQuotation) -> RequestForQuotation:
    if rfq.status == RequestForQuotation.Status.CLOSED:
        raise TransitionError("Closed RFQs cannot be cancelled.")
    rfq.status = RequestForQuotation.Status.CANCELLED
    rfq.save(update_fields=["status", "updated_at"])
    return rfq


# ---------------------------------------------------------------------------
# Supplier Quotation — comparison & selection
# ---------------------------------------------------------------------------
@transaction.atomic
def select_quotation(quotation: SupplierQuotation, *, user) -> PurchaseOrder:
    """Mark a quotation as the winner, reject the rest, and raise a draft PO.

    The RFQ is closed and a draft PurchaseOrder is created from the winning
    quotation's priced lines so it can flow through the normal PO issue path.
    """
    if quotation.status != SupplierQuotation.Status.RECEIVED:
        raise TransitionError("Only a received quotation can be selected.")
    if not quotation.lines.exists():
        raise TransitionError("Cannot select a quotation with no line items.")
    rfq = quotation.rfq
    if rfq.status not in {RequestForQuotation.Status.SENT, RequestForQuotation.Status.DRAFT}:
        raise TransitionError("Quotations can only be selected for an open RFQ.")

    po = PurchaseOrder.objects.create(
        vendor=quotation.vendor,
        project=rfq.project,
        requisition=rfq.requisition,
        payment_terms_days=quotation.payment_terms_days,
        created_by=user,
    )
    PurchaseOrderLine.objects.bulk_create([
        PurchaseOrderLine(
            purchase_order=po, material=ln.material, quantity=ln.quantity,
            unit_price=ln.unit_price, tax_rate=ln.tax_rate,
        )
        for ln in quotation.lines.all()
    ])
    po.recalculate_totals()

    quotation.status = SupplierQuotation.Status.SELECTED
    quotation.purchase_order = po
    quotation.save(update_fields=["status", "purchase_order", "updated_at"])

    rfq.quotations.exclude(pk=quotation.pk).filter(
        status=SupplierQuotation.Status.RECEIVED
    ).update(status=SupplierQuotation.Status.REJECTED)

    if rfq.status == RequestForQuotation.Status.SENT:
        rfq.status = RequestForQuotation.Status.CLOSED
        rfq.save(update_fields=["status", "updated_at"])
    return po


def reject_quotation(quotation: SupplierQuotation) -> SupplierQuotation:
    if quotation.status != SupplierQuotation.Status.RECEIVED:
        raise TransitionError("Only a received quotation can be rejected.")
    quotation.status = SupplierQuotation.Status.REJECTED
    quotation.save(update_fields=["status", "updated_at"])
    return quotation


# ---------------------------------------------------------------------------
# Purchase Order
# ---------------------------------------------------------------------------
def po_approval_rules_apply(po: PurchaseOrder) -> bool:
    """True if any active PO approval rule covers this PO's value band."""
    return any(
        r.matches_amount(po.total)
        for r in ApprovalRule.objects.filter(
            document_type=ApprovalDocumentType.PURCHASE_ORDER, is_active=True)
    )


@transaction.atomic
def submit_po_for_approval(po: PurchaseOrder, *, user) -> ApprovalRequest:
    if po.status != PurchaseOrder.Status.DRAFT:
        raise TransitionError("Only draft purchase orders can be submitted for approval.")
    if not po.lines.exists():
        raise TransitionError("Cannot submit a purchase order with no line items.")
    po.recalculate_totals()
    request = start_approval(
        po, document_type=ApprovalDocumentType.PURCHASE_ORDER, amount=po.total)
    if request is None:
        raise TransitionError("No approval rule applies to this purchase order.")
    return request


def issue_purchase_order(po: PurchaseOrder, *, user) -> PurchaseOrder:
    if po.status != PurchaseOrder.Status.DRAFT:
        raise TransitionError("Only draft purchase orders can be issued.")
    if not po.lines.exists():
        raise TransitionError("Cannot issue a purchase order with no line items.")
    # Enforce the approval matrix when one is configured for this value band.
    if po_approval_rules_apply(po) and not document_is_approved(po):
        raise TransitionError(
            "This purchase order must clear its approval workflow before it can be issued."
        )
    po.status = PurchaseOrder.Status.ISSUED
    po.approved_by = user
    po.approved_at = timezone.now()
    po.recalculate_totals(save=False)
    po.save(
        update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "subtotal",
            "tax_amount",
            "total",
            "updated_at",
        ]
    )
    # Mark the source requisition as converted, if any.
    pr = po.requisition
    if pr and pr.status == PurchaseRequisition.Status.APPROVED:
        pr.status = PurchaseRequisition.Status.CONVERTED
        pr.save(update_fields=["status", "updated_at"])
    # Snapshot this issued revision into the revision history.
    PurchaseOrderRevision.objects.create(
        purchase_order=po, revision=po.revision,
        subtotal=po.subtotal, tax_amount=po.tax_amount, total=po.total,
        note="Issued" if po.revision == 0 else f"Re-issued (rev {po.revision})",
        created_by=user,
    )
    # Draw down a linked blanket contract's consumed value.
    contract = po.contract
    if contract and contract.status == PurchaseContract.Status.ACTIVE and po.revision == 0:
        contract.consumed_value = (contract.consumed_value + po.total)
        contract.save(update_fields=["consumed_value", "updated_at"])
    log_action(po, action="Issued to vendor", user=user, to_status="ISSUED")
    notify(message=f"PO {po.number} issued to {po.vendor.name} ({po.total})",
           kind=Notification.Kind.PO, url=f"/purchase-orders/{po.pk}/")
    return po


@transaction.atomic
def reopen_purchase_order(po: PurchaseOrder, *, user) -> PurchaseOrder:
    """Re-open an issued PO for amendment (bumps the revision counter).

    Only allowed while nothing has been received against it.
    """
    if po.status != PurchaseOrder.Status.ISSUED:
        raise TransitionError("Only an issued purchase order can be re-opened.")
    if po.grns.filter(status=GoodsReceiptNote.Status.CONFIRMED).exists():
        raise TransitionError("Cannot revise a PO that already has confirmed receipts.")
    po.status = PurchaseOrder.Status.DRAFT
    po.revision += 1
    po.approved_by = None
    po.approved_at = None
    po.save(update_fields=["status", "revision", "approved_by", "approved_at", "updated_at"])
    return po


def email_purchase_order(po: PurchaseOrder) -> PurchaseOrder:
    """Email the PO summary to the vendor (console backend in dev)."""
    from django.conf import settings
    from django.core.mail import send_mail

    recipient = po.vendor.email
    if not recipient:
        raise TransitionError("The vendor has no email address on file.")
    body = (
        f"Dear {po.vendor.name},\n\n"
        f"Please find purchase order {po.number} (rev {po.revision}) for a total of "
        f"{po.total}.\n\nProject: {po.project.name}\n"
        f"Expected delivery: {po.expected_delivery_date or 'TBD'}\n\n"
        f"Regards,\nProcurement"
    )
    send_mail(
        subject=f"Purchase Order {po.number}",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=False,
    )
    po.emailed_at = timezone.now()
    po.save(update_fields=["emailed_at", "updated_at"])
    return po


def cancel_purchase_order(po: PurchaseOrder) -> PurchaseOrder:
    if po.status in {PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CLOSED}:
        raise TransitionError("Received or closed purchase orders cannot be cancelled.")
    if po.grns.filter(status=GoodsReceiptNote.Status.CONFIRMED).exists():
        raise TransitionError("Cannot cancel a PO that already has confirmed receipts.")
    po.status = PurchaseOrder.Status.CANCELLED
    po.save(update_fields=["status", "updated_at"])
    return po


def close_purchase_order(po: PurchaseOrder) -> PurchaseOrder:
    if po.status not in {
        PurchaseOrder.Status.RECEIVED,
        PurchaseOrder.Status.PARTIALLY_RECEIVED,
    }:
        raise TransitionError("Only (partially) received purchase orders can be closed.")
    po.status = PurchaseOrder.Status.CLOSED
    po.save(update_fields=["status", "updated_at"])
    return po


# ---------------------------------------------------------------------------
# Inventory / Stock Ledger
# ---------------------------------------------------------------------------
def post_stock_movement(*, material, project, movement, quantity: Decimal,
                        source=None, remarks: str = "", user=None) -> StockLedgerEntry:
    """Record a signed inventory movement and update the on-hand balance."""
    item, _ = StockItem.objects.select_for_update().get_or_create(
        material=material, project=project)
    item.quantity_on_hand = (item.quantity_on_hand + quantity)
    item.save(update_fields=["quantity_on_hand", "updated_at"])

    ct = ContentType.objects.get_for_model(type(source)) if source is not None else None
    return StockLedgerEntry.objects.create(
        material=material, project=project, movement=movement, quantity=quantity,
        balance_after=item.quantity_on_hand, remarks=remarks,
        content_type=ct, object_id=(source.pk if source is not None else None),
        created_by=user,
    )


# ---------------------------------------------------------------------------
# Goods Receipt Note
# ---------------------------------------------------------------------------
@transaction.atomic
def confirm_grn(grn: GoodsReceiptNote) -> GoodsReceiptNote:
    """Confirm a GRN: validate quantities, post receipts onto PO lines."""
    if grn.status != GoodsReceiptNote.Status.DRAFT:
        raise TransitionError("Only draft GRNs can be confirmed.")
    if grn.purchase_order.status not in {
        PurchaseOrder.Status.ISSUED,
        PurchaseOrder.Status.PARTIALLY_RECEIVED,
    }:
        raise TransitionError(
            "Goods can only be received against an issued purchase order."
        )
    lines = list(grn.lines.select_related("po_line"))
    if not lines:
        raise TransitionError("Cannot confirm a GRN with no line items.")

    for line in lines:
        if line.po_line.purchase_order_id != grn.purchase_order_id:
            raise TransitionError(
                "GRN line references a PO line from a different purchase order."
            )
        if line.accepted_quantity > line.received_quantity:
            raise TransitionError(
                "Accepted quantity cannot exceed received quantity."
            )
        prospective = line.po_line.received_quantity + line.accepted_quantity
        if prospective > line.po_line.quantity:
            raise TransitionError(
                f"Receiving {line.accepted_quantity} of {line.po_line.material} "
                f"exceeds the ordered quantity ({line.po_line.quantity})."
            )

    # Post accepted quantities onto the PO lines and into the stock ledger.
    project = grn.purchase_order.project
    for line in lines:
        po_line = line.po_line
        po_line.received_quantity += line.accepted_quantity
        po_line.save(update_fields=["received_quantity"])
        if line.accepted_quantity > 0:
            post_stock_movement(
                material=po_line.material, project=project,
                movement=StockLedgerEntry.Movement.RECEIPT,
                quantity=line.accepted_quantity, source=grn,
                remarks=f"GRN {grn.number}", user=grn.received_by,
            )

    grn.status = GoodsReceiptNote.Status.CONFIRMED
    grn.save(update_fields=["status", "updated_at"])

    grn.purchase_order.refresh_receipt_status()
    log_action(grn, action="Confirmed; stock posted", user=grn.received_by, to_status="CONFIRMED")
    notify(message=f"GRN {grn.number} confirmed against {grn.purchase_order.number}",
           kind=Notification.Kind.GRN, url=f"/grns/{grn.pk}/")
    return grn


@transaction.atomic
def cancel_grn(grn: GoodsReceiptNote) -> GoodsReceiptNote:
    """Cancel a confirmed/draft GRN, reversing any posted quantities + stock."""
    if grn.status == GoodsReceiptNote.Status.CANCELLED:
        raise TransitionError("GRN is already cancelled.")
    if grn.status == GoodsReceiptNote.Status.CONFIRMED:
        project = grn.purchase_order.project
        for line in grn.lines.select_related("po_line"):
            po_line = line.po_line
            po_line.received_quantity = max(
                Decimal("0.000"), po_line.received_quantity - line.accepted_quantity
            )
            po_line.save(update_fields=["received_quantity"])
            if line.accepted_quantity > 0:
                post_stock_movement(
                    material=po_line.material, project=project,
                    movement=StockLedgerEntry.Movement.ADJUSTMENT,
                    quantity=-line.accepted_quantity, source=grn,
                    remarks=f"Reversal of GRN {grn.number}", user=grn.received_by,
                )
        grn.purchase_order.refresh_receipt_status()
    grn.status = GoodsReceiptNote.Status.CANCELLED
    grn.save(update_fields=["status", "updated_at"])
    return grn


# ---------------------------------------------------------------------------
# Quality Inspection
# ---------------------------------------------------------------------------
def submit_inspection(inspection: QualityInspection, *, user) -> QualityInspection:
    """QC approval: derive pass/fail from the checklist and stamp the inspector.

    Passes only if every checklist item is PASS or NA (and there is at least one).
    """
    if inspection.status != QualityInspection.Status.PENDING:
        raise TransitionError("This inspection has already been completed.")
    items = list(inspection.items.all())
    if not items:
        raise TransitionError("Add at least one checklist item before submitting.")
    if any(i.result == QCChecklistItem.Result.PENDING for i in items):
        raise TransitionError("Every checklist item must be marked pass/fail/NA first.")

    failed = any(i.result == QCChecklistItem.Result.FAIL for i in items)
    inspection.status = (
        QualityInspection.Status.FAILED if failed else QualityInspection.Status.PASSED)
    inspection.inspected_by = user
    inspection.inspected_at = timezone.now()
    inspection.save(update_fields=["status", "inspected_by", "inspected_at", "updated_at"])
    return inspection


# ---------------------------------------------------------------------------
# Purchase Returns
# ---------------------------------------------------------------------------
@transaction.atomic
def confirm_return(ret: PurchaseReturn) -> PurchaseReturn:
    """Confirm a return: validate quantities, reverse received qty + stock."""
    if ret.status != PurchaseReturn.Status.DRAFT:
        raise TransitionError("Only draft returns can be confirmed.")
    lines = list(ret.lines.select_related("po_line__material"))
    if not lines:
        raise TransitionError("Cannot confirm a return with no line items.")

    for line in lines:
        if line.po_line.purchase_order_id != ret.purchase_order_id:
            raise TransitionError(
                "Return line references a PO line from a different purchase order.")
        if line.quantity > line.po_line.received_quantity:
            raise TransitionError(
                f"Cannot return {line.quantity} of {line.po_line.material}; only "
                f"{line.po_line.received_quantity} was received.")

    project = ret.purchase_order.project
    for line in lines:
        po_line = line.po_line
        po_line.received_quantity -= line.quantity
        po_line.save(update_fields=["received_quantity"])
        post_stock_movement(
            material=po_line.material, project=project,
            movement=StockLedgerEntry.Movement.RETURN,
            quantity=-line.quantity, source=ret,
            remarks=f"Return {ret.number}", user=ret.created_by)

    ret.status = PurchaseReturn.Status.CONFIRMED
    ret.save(update_fields=["status", "updated_at"])
    ret.purchase_order.refresh_receipt_status()
    return ret


@transaction.atomic
def cancel_return(ret: PurchaseReturn) -> PurchaseReturn:
    """Cancel a return, restoring received quantities + stock if it was confirmed."""
    if ret.status == PurchaseReturn.Status.CANCELLED:
        raise TransitionError("Return is already cancelled.")
    if ret.status == PurchaseReturn.Status.CONFIRMED:
        project = ret.purchase_order.project
        for line in ret.lines.select_related("po_line"):
            po_line = line.po_line
            po_line.received_quantity += line.quantity
            po_line.save(update_fields=["received_quantity"])
            post_stock_movement(
                material=po_line.material, project=project,
                movement=StockLedgerEntry.Movement.ADJUSTMENT,
                quantity=line.quantity, source=ret,
                remarks=f"Reversal of return {ret.number}", user=ret.created_by)
        ret.purchase_order.refresh_receipt_status()
    ret.status = PurchaseReturn.Status.CANCELLED
    ret.save(update_fields=["status", "updated_at"])
    return ret


# ---------------------------------------------------------------------------
# Purchase Contracts
# ---------------------------------------------------------------------------
def activate_contract(contract: PurchaseContract) -> PurchaseContract:
    if contract.status != PurchaseContract.Status.DRAFT:
        raise TransitionError("Only draft contracts can be activated.")
    if contract.end_date < contract.start_date:
        raise TransitionError("Contract end date cannot precede the start date.")
    contract.status = PurchaseContract.Status.ACTIVE
    contract.save(update_fields=["status", "updated_at"])
    return contract


def terminate_contract(contract: PurchaseContract) -> PurchaseContract:
    if contract.status not in {PurchaseContract.Status.ACTIVE, PurchaseContract.Status.DRAFT}:
        raise TransitionError("Only draft or active contracts can be terminated.")
    contract.status = PurchaseContract.Status.TERMINATED
    contract.save(update_fields=["status", "updated_at"])
    return contract


@transaction.atomic
def renew_contract(contract: PurchaseContract, *, start_date, end_date, user) -> PurchaseContract:
    """Clone an active/expired contract's pricing into a fresh contract."""
    if contract.status not in {
        PurchaseContract.Status.ACTIVE, PurchaseContract.Status.EXPIRED,
    }:
        raise TransitionError("Only active or expired contracts can be renewed.")
    new = PurchaseContract.objects.create(
        title=contract.title, vendor=contract.vendor, contract_type=contract.contract_type,
        status=PurchaseContract.Status.ACTIVE, start_date=start_date, end_date=end_date,
        total_value=contract.total_value, auto_renew=contract.auto_renew,
        renewed_from=contract, terms=contract.terms, created_by=user,
    )
    ContractLine.objects.bulk_create([
        ContractLine(contract=new, material=ln.material, unit_price=ln.unit_price,
                     tax_rate=ln.tax_rate, max_quantity=ln.max_quantity)
        for ln in contract.lines.all()
    ])
    contract.status = PurchaseContract.Status.RENEWED
    contract.save(update_fields=["status", "updated_at"])
    return new


# ---------------------------------------------------------------------------
# Vendor Bill — 3-way matching
# ---------------------------------------------------------------------------
def run_three_way_match(bill: VendorBill, *, price_tolerance=Decimal("0.01")) -> VendorBill:
    """Compare the bill against PO prices and received quantities.

    The match passes when, for every billed PO line:
      * the billed unit price is within ``price_tolerance`` of the PO price, and
      * the billed quantity does not exceed the accepted (received) quantity.
    """
    bill.recalculate_totals(save=False)
    exceptions: list[str] = []

    for line in bill.lines.select_related("po_line__material"):
        po_line = line.po_line
        if po_line.purchase_order_id != bill.purchase_order_id:
            exceptions.append(
                f"Line for {po_line.material} is not part of PO {bill.purchase_order.number}."
            )
            continue
        if abs(line.unit_price - po_line.unit_price) > price_tolerance:
            exceptions.append(
                f"Price mismatch for {po_line.material}: billed {line.unit_price} "
                f"vs PO {po_line.unit_price}."
            )
        if line.quantity > po_line.received_quantity:
            exceptions.append(
                f"Quantity for {po_line.material} ({line.quantity}) exceeds received "
                f"quantity ({po_line.received_quantity})."
            )

    if exceptions:
        bill.match_status = VendorBill.MatchStatus.EXCEPTION
        bill.match_notes = "\n".join(exceptions)
        bill.status = VendorBill.Status.DISPUTED
    else:
        bill.match_status = VendorBill.MatchStatus.MATCHED
        bill.match_notes = "3-way match successful."
        bill.status = VendorBill.Status.MATCHED
    bill.save(
        update_fields=[
            "match_status",
            "match_notes",
            "status",
            "subtotal",
            "tax_amount",
            "total",
            "updated_at",
        ]
    )
    return bill


def approve_bill(bill: VendorBill) -> VendorBill:
    if bill.status != VendorBill.Status.MATCHED:
        raise TransitionError("Only successfully matched bills can be approved.")
    bill.status = VendorBill.Status.APPROVED
    bill.save(update_fields=["status", "updated_at"])
    return bill


def mark_bill_paid(bill: VendorBill) -> VendorBill:
    if bill.status != VendorBill.Status.APPROVED:
        raise TransitionError("Only approved bills can be marked paid.")
    bill.status = VendorBill.Status.PAID
    bill.save(update_fields=["status", "updated_at"])
    log_action(bill, action="Marked paid", to_status="PAID")
    return bill


# ---------------------------------------------------------------------------
# Supplier Payments
# ---------------------------------------------------------------------------
@transaction.atomic
def post_payment(payment: Payment) -> Payment:
    """Mark a payment as PAID. If it fully settles an approved bill, close the bill.

    Supports partial payments (a bill may have several payments) and advances
    (payments with no linked bill).
    """
    if payment.status != Payment.Status.PENDING:
        raise TransitionError("Only pending payments can be posted.")
    payment.status = Payment.Status.PAID
    payment.save(update_fields=["status", "updated_at"])

    bill = payment.bill
    if bill and bill.status == VendorBill.Status.APPROVED and bill.outstanding <= Decimal("0.00"):
        bill.status = VendorBill.Status.PAID
        bill.save(update_fields=["status", "updated_at"])
    log_action(payment, action=f"Payment posted ({payment.amount})", to_status="PAID")
    notify(message=f"Payment {payment.number} of {payment.amount} to {payment.vendor.name}",
           kind=Notification.Kind.PAYMENT, recipient_role="ACCOUNTANT",
           url="/payments/")
    return payment


@transaction.atomic
def cancel_payment(payment: Payment) -> Payment:
    if payment.status == Payment.Status.CANCELLED:
        raise TransitionError("Payment is already cancelled.")
    was_paid = payment.status == Payment.Status.PAID
    payment.status = Payment.Status.CANCELLED
    payment.save(update_fields=["status", "updated_at"])
    # If reversing a payment un-settles a PAID bill, drop it back to APPROVED.
    bill = payment.bill
    if was_paid and bill and bill.status == VendorBill.Status.PAID and bill.outstanding > Decimal("0.00"):
        bill.status = VendorBill.Status.APPROVED
        bill.save(update_fields=["status", "updated_at"])
    return payment
