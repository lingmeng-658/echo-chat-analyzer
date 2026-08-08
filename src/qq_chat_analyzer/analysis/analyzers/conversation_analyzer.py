"""Conversation-level analysis over normalized chat messages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..models import ConversationReport, ConversationSummary
from ..timestamps import to_epoch_seconds
from ...message import ChatMessage


class ConversationAnalyzer:
    """Report volume, time span, and participation per conversation."""

    def analyze(
        self,
        messages: Sequence[ChatMessage],
        conversation_names: Mapping[str, str] | None = None,
    ) -> ConversationReport:
        """Return one summary per conversation in first-seen order.

        ``conversation_names`` optionally maps a ``conversation_id`` to a
        human readable name. Names are supplied by the caller so this
        analyzer stays independent of any chat source.
        """
        grouped: dict[str | None, _ConversationStats] = {}

        for message in messages:
            stats = grouped.setdefault(
                message.conversation_id,
                _ConversationStats(),
            )
            stats.add(message)

        return ConversationReport(
            conversation_count=len(grouped),
            conversations=tuple(
                stats.to_summary(
                    conversation_id,
                    _display_name_for(conversation_id, conversation_names),
                )
                for conversation_id, stats in grouped.items()
            ),
        )


class _ConversationStats:
    """Mutable accumulator for one conversation."""

    __slots__ = ("message_count", "speakers", "start", "end")

    def __init__(self) -> None:
        self.message_count = 0
        self.speakers: set[str] = set()
        self.start: int | None = None
        self.end: int | None = None

    def add(self, message: ChatMessage) -> None:
        self.message_count += 1
        self.speakers.add(message.sender)

        epoch_seconds = to_epoch_seconds(message.timestamp)
        if epoch_seconds is None:
            return
        if self.start is None or epoch_seconds < self.start:
            self.start = epoch_seconds
        if self.end is None or epoch_seconds > self.end:
            self.end = epoch_seconds

    def to_summary(
        self,
        conversation_id: str | None,
        display_name: str | None = None,
    ) -> ConversationSummary:
        duration_seconds = (
            self.end - self.start
            if self.start is not None and self.end is not None
            else None
        )
        return ConversationSummary(
            conversation_id=conversation_id,
            display_name=display_name,
            message_count=self.message_count,
            speaker_count=len(self.speakers),
            start_timestamp=self.start,
            end_timestamp=self.end,
            duration_seconds=duration_seconds,
        )


def _display_name_for(
    conversation_id: str | None,
    conversation_names: Mapping[str, str] | None,
) -> str | None:
    """Look up a friendly name for one conversation id.

    Names come from the caller, so this analyzer never has to know how QQ or
    WeChat label a conversation.
    """
    if conversation_id is None or not conversation_names:
        return None
    name = conversation_names.get(conversation_id)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None
