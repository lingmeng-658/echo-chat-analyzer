"""Privacy-safe import summary domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Describe the result of importing chat data without raw content."""

    platform: str
    message_count: int
    valid_text_count: int
    warnings: tuple[str, ...] = ()
    format: str | None = None
