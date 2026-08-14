"""Internal import pipeline result that may carry parsed messages."""

from __future__ import annotations

from dataclasses import dataclass

from ..message import ChatMessage
from ..rich_message import RichMessage
from .import_result import ImportResult


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    """Internal pipeline result combining public summary with messages."""

    result: ImportResult
    processed_message_count: int
    messages: tuple[ChatMessage, ...]
    rich_messages: tuple[RichMessage, ...] = ()
