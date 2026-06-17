"""Template helpers for the procurement frontend."""
from django import template

register = template.Library()

# Map document/status codes to Bootstrap 5.3 contextual badge classes.
_BADGE = {
    # neutral / in-progress
    "DRAFT": "badge-soft-slate",
    "PLANNING": "badge-soft-blue",
    "PENDING": "badge-soft-amber",
    "SUBMITTED": "badge-soft-amber",
    "ON_HOLD": "badge-soft-amber",
    # positive
    "ACTIVE": "badge-soft-green",
    "APPROVED": "badge-soft-green",
    "MATCHED": "badge-soft-green",
    "CONFIRMED": "badge-soft-green",
    "RECEIVED": "badge-soft-green",
    "PAID": "badge-soft-green",
    # routing / info
    "ISSUED": "badge-soft-indigo",
    "CONVERTED": "badge-soft-indigo",
    "PARTIALLY_RECEIVED": "badge-soft-blue",
    "CLOSED": "badge-soft-slate",
    "COMPLETED": "badge-soft-slate",
    # negative
    "REJECTED": "badge-soft-red",
    "CANCELLED": "badge-soft-red",
    "DISPUTED": "badge-soft-red",
    "EXCEPTION": "badge-soft-red",
}


@register.filter
def status_badge(value):
    """Return the badge CSS class for a status code (defaults to slate)."""
    return _BADGE.get(str(value).upper(), "badge-soft-slate")


@register.filter
def status_color(value):
    """Return just the colour name (green/amber/red/blue/indigo/slate)."""
    return _BADGE.get(str(value).upper(), "badge-soft-slate").rsplit("-", 1)[-1]
