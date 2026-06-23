"""Tiny shared helpers."""

from __future__ import annotations

import hashlib


def sha1_id(*parts) -> str:
    """Stable id from whatever fields matter."""
    joined = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def short_metric(type_str: str) -> str:
    """Drop the long HealthKit prefix."""
    for prefix in (
        "HKQuantityTypeIdentifier",
        "HKCategoryTypeIdentifier",
        "HKDataType",
        "HKWorkoutActivityType",
    ):
        if type_str.startswith(prefix):
            return type_str[len(prefix):]
    return type_str


def to_float(value):
    """Blank strings become None."""
    if value is None:
        return None
    value = value.strip() if isinstance(value, str) else value
    if value == "" or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value):
    f = to_float(value)
    return None if f is None else int(f)
