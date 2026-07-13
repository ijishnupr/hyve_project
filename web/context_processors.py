"""Template context processors for the web frontend."""
from procurement import services


def notifications(request):
    """Expose the unread-notification count to every template (navbar badge)."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    try:
        count = services.notifications_for(request.user).filter(is_read=False).count()
    except Exception:
        count = 0
    return {"unread_notifications": count}
