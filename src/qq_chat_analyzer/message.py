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
    message_id: str | None = None
    sender_id: str | None = None
    conversation_id: str | None = None
    is_system: bool = False
    recalled: bool = False
    sender_remark: str | None = None
    sender_nickname: str | None = None
    sender_contextual_name: str | None = None
