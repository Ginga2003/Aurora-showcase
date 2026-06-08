import os
import json
from django import template
from django.utils.safestring import mark_safe
from music.type_rules import SECONDARY_TYPE_SET, split_song_types

register = template.Library()

@register.filter
def bust_url(field):
    """Append file mtime as ?v= cache-buster. Skips default assets."""
    if not field:
        return ''
    try:
        url = field.url
        name = str(field.name)
        if 'default' in name:
            return url
        mtime = int(os.path.getmtime(field.path))
        return f"{url}?v={mtime}"
    except Exception:
        return getattr(field, 'url', '')

@register.filter
def split_artists(value):
    """
    Splits a string of artists by the pipe symbol '|' and returns a list.
    Handles extra whitespace and empty values.
    """
    if not value:
        return []
    # Force to string and split by pipe
    artists = [a.strip() for a in str(value).split('|') if a.strip()]
    return artists


@register.filter
def split_types(value):
    """Same pipe-split convention as artists, applied to song_type."""
    return split_song_types(value)


@register.filter
def display_types(value):
    """Pretty-print a multi-type CharField: 'Game | Anime' -> 'Game, Anime'."""
    return ', '.join(split_song_types(value))


@register.filter
def is_secondary_type(value):
    """Return True when the display type is one of the exclusive secondary types."""
    return str(value).strip() in SECONDARY_TYPE_SET


@register.simple_tag
def secondary_type_names_json():
    """Expose secondary type names to frontend scripts."""
    return mark_safe(json.dumps(sorted(SECONDARY_TYPE_SET)))
