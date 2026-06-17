"""
Business logic for procurement state transitions.

Kept out of views/serializers so the rules are testable in isolation and
reused by the API, the admin and any background tasks.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    GoodsReceiptNote,
    PurchaseOrder,
    PurchaseRequisition,
    VendorBill,
)


class TransitionError(Exception):
    """Raised when a requested state transition is not allowed."""


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
    return pr


def approve_requisition(pr: PurchaseRequisition, *, user) -> PurchaseRequisition:
    if pr.status != PurchaseRequisition.Status.SUBMITTED:
        raise TransitionError("Only submitted requisitions can be approved.")
    pr.status = PurchaseRequisition.Status.APPROVED
    pr.approved_by = user
    pr.approved_at = timezone.now()
    pr.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
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
# Purchase Order
# ---------------------------------------------------------------------------
def issue_purchase_order(po: PurchaseOrder, *, user) -> PurchaseOrder:
    if po.status != PurchaseOrder.Status.DRAFT:
        raise TransitionError("Only draft purchase orders can be issued.")
    if not po.lines.exists():
        raise TransitionError("Cannot issue a purchase order with no line items.")
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

    # Post accepted quantities onto the PO lines.
    for line in lines:
        po_line = line.po_line
        po_line.received_quantity += line.accepted_quantity
        po_line.save(update_fields=["received_quantity"])

    grn.status = GoodsReceiptNote.Status.CONFIRMED
    grn.save(update_fields=["status", "updated_at"])

    grn.purchase_order.refresh_receipt_status()
    return grn


@transaction.atomic
def cancel_grn(grn: GoodsReceiptNote) -> GoodsReceiptNote:
    """Cancel a confirmed/draft GRN, reversing any posted quantities."""
    if grn.status == GoodsReceiptNote.Status.CANCELLED:
        raise TransitionError("GRN is already cancelled.")
    if grn.status == GoodsReceiptNote.Status.CONFIRMED:
        for line in grn.lines.select_related("po_line"):
            po_line = line.po_line
            po_line.received_quantity = max(
                Decimal("0.000"), po_line.received_quantity - line.accepted_quantity
            )
            po_line.save(update_fields=["received_quantity"])
        grn.purchase_order.refresh_receipt_status()
    grn.status = GoodsReceiptNote.Status.CANCELLED
    grn.save(update_fields=["status", "updated_at"])
    return grn


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
    return bill
