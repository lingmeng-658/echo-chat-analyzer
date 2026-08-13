"""Source-neutral conversation session segmentation and statistics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from ..message import ChatMessage
from .identity import stable_sender_key
from .timestamps import to_epoch_seconds


DEFAULT_SESSION_THRESHOLD_SECONDS = 30 * 60


@dataclass(frozen=True, slots=True)
class ConversationSession:
    """One continuous run of chat messages."""

    start_timestamp: int | None
    end_timestamp: int | None
    duration_seconds: int
    message_count: int
    initiator: str
    initiator_sender_key: str | None = None


@dataclass(frozen=True, slots=True)
class PrivateSessionStats:
    """Private-chat initiator counts and shares without identity guessing."""

    self_initiated_count: int
    peer_initiated_count: int
    unknown_initiated_count: int
    self_to_peer_ratio: float | None
    self_initiated_share: float
    peer_initiated_share: float
    unknown_initiated_share: float


@dataclass(frozen=True, slots=True)
class ConversationSessionReport:
    """Aggregate session statistics for one analyzed conversation."""

    conversation_type: str
    threshold_seconds: int
    session_count: int
    average_duration_seconds: float
    median_duration_seconds: float
    longest_duration_seconds: int
    average_message_count: float
    sessions: tuple[ConversationSession, ...] = ()
    private_stats: PrivateSessionStats | None = None


def analyze_conversation_sessions(
    messages: Sequence[ChatMessage],
    *,
    threshold_seconds: int = DEFAULT_SESSION_THRESHOLD_SECONDS,
) -> ConversationSessionReport:
    """Split messages when adjacent valid timestamps exceed the threshold.

    Invalid and zero timestamps remain part of the current session but never
    create a boundary, so unusable clock data cannot distort session spans.
    """
    if threshold_seconds < 0:
        raise ValueError("threshold_seconds must be non-negative")

    conversation_type = _conversation_type(messages)
    sessions = _split_sessions(
        messages,
        conversation_type=conversation_type,
        threshold_seconds=threshold_seconds,
    )
    durations = tuple(session.duration_seconds for session in sessions)
    session_count = len(sessions)
    return ConversationSessionReport(
        conversation_type=conversation_type,
        threshold_seconds=threshold_seconds,
        session_count=session_count,
        average_duration_seconds=(
            sum(durations) / session_count if session_count else 0.0
        ),
        median_duration_seconds=(float(median(durations)) if durations else 0.0),
        longest_duration_seconds=max(durations, default=0),
        average_message_count=(
            sum(session.message_count for session in sessions) / session_count
            if session_count
            else 0.0
        ),
        sessions=sessions,
        private_stats=(
            _private_stats(sessions)
            if conversation_type == "private"
            else None
        ),
    )


def _split_sessions(
    messages: Sequence[ChatMessage],
    *,
    conversation_type: str,
    threshold_seconds: int,
) -> tuple[ConversationSession, ...]:
    if not messages:
        return ()

    groups: list[list[ChatMessage]] = [[]]
    last_valid_timestamp: int | None = None
    for message in messages:
        timestamp = to_epoch_seconds(message.timestamp)
        if (
            timestamp is not None
            and last_valid_timestamp is not None
            and timestamp - last_valid_timestamp > threshold_seconds
        ):
            groups.append([])
        groups[-1].append(message)
        if timestamp is not None:
            last_valid_timestamp = timestamp

    return tuple(
        _build_session(group, conversation_type=conversation_type)
        for group in groups
    )


def _build_session(
    messages: Sequence[ChatMessage],
    *,
    conversation_type: str,
) -> ConversationSession:
    timestamps = tuple(
        timestamp
        for message in messages
        if (timestamp := to_epoch_seconds(message.timestamp)) is not None
    )
    start_timestamp = min(timestamps, default=None)
    end_timestamp = max(timestamps, default=None)
    initiator, initiator_sender_key = _initiator(
        messages[0],
        conversation_type=conversation_type,
    )
    return ConversationSession(
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        duration_seconds=(
            end_timestamp - start_timestamp
            if start_timestamp is not None and end_timestamp is not None
            else 0
        ),
        message_count=len(messages),
        initiator=initiator,
        initiator_sender_key=initiator_sender_key,
    )


def _initiator(
    message: ChatMessage,
    *,
    conversation_type: str,
) -> tuple[str, str | None]:
    sender_key = stable_sender_key(message)
    if conversation_type == "private":
        if message.is_self is True:
            return "self", sender_key
        if message.is_self is False:
            return "peer", sender_key
        return "unknown", sender_key
    if conversation_type == "group":
        return sender_key, sender_key
    return "unknown", sender_key


def _conversation_type(messages: Sequence[ChatMessage]) -> str:
    known_types = {
        message.conversation_type
        for message in messages
        if message.conversation_type in ("private", "group")
    }
    if len(known_types) == 1:
        return known_types.pop()
    return "unknown"


def _private_stats(
    sessions: tuple[ConversationSession, ...],
) -> PrivateSessionStats:
    session_count = len(sessions)
    self_count = sum(session.initiator == "self" for session in sessions)
    peer_count = sum(session.initiator == "peer" for session in sessions)
    unknown_count = sum(session.initiator == "unknown" for session in sessions)
    return PrivateSessionStats(
        self_initiated_count=self_count,
        peer_initiated_count=peer_count,
        unknown_initiated_count=unknown_count,
        self_to_peer_ratio=(self_count / peer_count if peer_count else None),
        self_initiated_share=self_count / session_count if session_count else 0.0,
        peer_initiated_share=peer_count / session_count if session_count else 0.0,
        unknown_initiated_share=(
            unknown_count / session_count if session_count else 0.0
        ),
    )
