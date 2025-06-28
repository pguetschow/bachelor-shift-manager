from django import template
from rostering_app.utils import get_shift_display_name

register = template.Library()

@register.filter
def multiply(value, arg):
    return value * arg

@register.filter
def shift_display_name(shift_name):
    """Convert shift name to German display name."""
    return get_shift_display_name(shift_name) 