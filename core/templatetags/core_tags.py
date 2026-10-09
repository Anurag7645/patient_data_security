"""Custom template tags for the core app."""

from django import template

register = template.Library()


@register.filter
def get_role(user):
    """Return the role string for a user, or empty string if no profile."""
    try:
        return user.profile.role
    except Exception:
        return ""
