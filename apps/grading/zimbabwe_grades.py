"""
Curated Zimbabwe flue-cured style grade codes for AI-constrained suggestions.

These mirror the broad TIMB / auction letter–digit ladder (Virginia flue-cured).
Update `GRADES_VERSION` when the catalogue changes; persist version in API responses.
"""

from __future__ import annotations

GRADES_VERSION = "zw-flue-curated-v1"

# Letter groups A (finest) … X (reject/off-type), with typical numeric positions.
# Not exhaustive of every seasonal TIMB sheet; expand via DB later.
_ALLOWED: list[str] = []
for letter, max_n in (
    ("A", 6),
    ("B", 6),
    ("C", 6),
    ("D", 6),
    ("E", 6),
    ("F", 6),
    ("G", 6),
    ("H", 6),
    ("K", 6),
    ("L", 6),
    ("M", 6),
    ("N", 1),  # single-grade style in some schedules
    ("O", 4),
    ("P", 4),
    ("R", 3),
    ("S", 4),
    ("T", 4),
    ("U", 3),
    ("V", 4),
    ("X", 4),
):
    if max_n == 1:
        _ALLOWED.append(letter)
    else:
        for i in range(1, max_n + 1):
            _ALLOWED.append(f"{letter}{i}")

ALLOWED_GRADES: frozenset[str] = frozenset(s.upper() for s in _ALLOWED)


def allowed_grades_sorted() -> list[str]:
    return sorted(ALLOWED_GRADES)
