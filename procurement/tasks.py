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


@shared_task
def send_contract_expiry_alerts(days: int = 30) -> int:
    """Raise notifications for active contracts expiring within ``days`` days."""
    from datetime import timedelta

    from .models import Notification, PurchaseContract

    cutoff = timezone.localdate() + timedelta(days=days)
    expiring = PurchaseContract.objects.filter(
        status=PurchaseContract.Status.ACTIVE, end_date__lte=cutoff)
    created = 0
    for c in expiring:
        already = Notification.objects.filter(
            kind=Notification.Kind.CONTRACT, url=f"/contracts/{c.pk}/", is_read=False).exists()
        if already:
            continue
        Notification.objects.create(
            kind=Notification.Kind.CONTRACT, recipient_role="PROCUREMENT_MANAGER",
            message=f"Contract {c.number} ({c.title}) expires on {c.end_date}",
            url=f"/contracts/{c.pk}/")
        created += 1
    return created
