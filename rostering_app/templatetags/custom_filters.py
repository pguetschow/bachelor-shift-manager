from django import template

from rostering_app.utils import get_shift_display_name

register = template.Library()


@register.filter
def multiply(value, arg):
    """Multiply two values."""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def shift_display_name(shift_name):
    """Convert shift name to German display name."""
    return get_shift_display_name(shift_name)


@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary."""
    return dictionary.get(key)


@register.filter
def floatformat(value, decimals=1):
    """Format a float to specified decimal places."""
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return value


@register.filter
def add(value, arg):
    """Add two values together."""
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        try:
            return float(value) + float(arg)
        except (ValueError, TypeError):
            return value


@register.filter
def cut(value, arg):
    """Remove all values of arg from the given string."""
    try:
        return value.replace(arg, '')
    except AttributeError:
        return value
