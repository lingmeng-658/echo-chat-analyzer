"""Internal import pipeline result that may carry parsed messages."""

from __future__ import annotations

from dataclasses import dataclass

from ..message import ChatMessage
from .import_result import ImportResult


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    """Internal pipeline result combining public summary with messages."""

    result: ImportResult
    messages: tuple[ChatMessage, ...]
