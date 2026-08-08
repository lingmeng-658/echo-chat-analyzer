"""Tolerant timestamp normalization for report analyzers."""

from __future__ import annotations

from datetime import datetime, timezone


_SECOND_BOUNDS = (10**8, 10**11)
_MILLISECOND_DIVISOR = 1000
_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
)


def to_epoch_seconds(timestamp: int | float | str | None) -> int | None:
    """Return whole epoch seconds, or None when the value is unusable.

    Parsers accept any int, float, or string timestamp, so this helper never
    raises and simply reports None for values it cannot interpret.
    """
    if isinstance(timestamp, bool) or timestamp is None:
        return None
    if isinstance(timestamp, (int, float)):
        return _normalize_numeric(float(timestamp))
    if isinstance(timestamp, str):
        return _parse_text(timestamp.strip())
    return None


def to_utc_datetime(timestamp: int | float | str | None) -> datetime | None:
    """Return a UTC datetime for a supported timestamp, or None."""
    epoch_seconds = to_epoch_seconds(timestamp)
    if epoch_seconds is None:
        return None
    try:
        return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _normalize_numeric(value: float) -> int | None:
    if value != value or value in (float("inf"), float("-inf")):
        return None
    if value < 0:
        return None
    if value >= _SECOND_BOUNDS[1]:
        value /= _MILLISECOND_DIVISOR
    return int(value)


def _parse_text(text: str) -> int | None:
    if not text:
        return None

    try:
        return _normalize_numeric(float(text))
    except ValueError:
        pass

    isotext = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(isotext)
    except ValueError:
        parsed = _parse_known_formats(text)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _parse_known_formats(text: str) -> datetime | None:
    for datetime_format in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, datetime_format)
        except ValueError:
            continue
    return None