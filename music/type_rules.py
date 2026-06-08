"""Shared song type rules.

Secondary types are exclusive: when a song is classified as one of these,
the final song_type should be exactly that secondary type. The tuple order is
highest priority first.
"""

TYPE_SEPARATOR = " | "

SECONDARY_TYPE_PRIORITY = (
    "Blossom",
    "Infinity",
    "Memento Mori",
    "Oboete",
    "Love",
    "Omni Force",
    "ElectronicNeko",
    "Ark",
    "Genso",
    "BloodBath",
    "Flan",
    "Memories",
    "Alice",
    "Miriya",
    "Calamity",
    "Demon and Hallow",
    "Scarlet",
    "Alive or Death",
    "Recovery",
)

SECONDARY_TYPE_SET = frozenset(SECONDARY_TYPE_PRIORITY)


def split_song_types(value):
    """Split a pipe-separated song_type value into clean members."""
    if not value:
        return []
    return [type_name.strip() for type_name in str(value).split("|") if type_name.strip()]


def highest_priority_secondary_type(types):
    """Return the highest-priority secondary type found in an iterable."""
    type_set = set(types)
    for type_name in SECONDARY_TYPE_PRIORITY:
        if type_name in type_set:
            return type_name
    return None


def normalize_song_type(types):
    """Normalize song types, enforcing secondary-type exclusivity."""
    members = split_song_types(types) if isinstance(types, str) else [t for t in types if t]
    secondary_type = highest_priority_secondary_type(members)
    if secondary_type:
        return secondary_type
    return TYPE_SEPARATOR.join(dict.fromkeys(members))
