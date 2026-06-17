"""Celery tasks for asynchronous procurement work."""
from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone


@shared_task
def notify_po_issued(po_id: int) -> str:
    """Email the vendor when a purchase order is issued.

    Kept deliberately simple; wire to a real template in production.
    """
    from .models import PurchaseOrder

    try:
        po = PurchaseOrder.objects.select_related("vendor").get(pk=po_id)
    except PurchaseOrder.DoesNotExist:
        return "po-not-found"

    if not po.vendor.email:
        return "vendor-has-no-email"

    send_mail(
        subject=f"Purchase Order {po.number}",
        message=(
            f"Dear {po.vendor.name},\n\n"
            f"Please find purchase order {po.number} dated {po.order_date} "
            f"for a total of {po.total}.\n\nRegards,\nProcurement Team"
        ),
        from_email=None,
        recipient_list=[po.vendor.email],
        fail_silently=True,
    )
    return "sent"


@shared_task
def flag_overdue_bills() -> int:
    """Mark approved bills past their due date — run on a Celery beat schedule."""
    from .models import VendorBill

    overdue = VendorBill.objects.filter(
        status=VendorBill.Status.APPROVED,
        due_date__lt=timezone.localdate(),
    )
    return overdue.count()
