"""Source-neutral chat message model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A text-bearing chat message normalized for analysis."""

    timestamp: int | float | str
    sender: str
    message_type: str
    text: str
    platform: str = "unknown"
    source_type: str | int | None = None
