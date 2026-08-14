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
    initiator_is_self: bool | None = None


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
class GroupSessionStats:
    """Group-chat initiator aggregates over stable sender identities."""

    self_initiated_count: int | None
    self_initiated_share: float | None
    top_initiator_sender_key: str | None
    top_initiated_count: int
    top_initiated_share: float


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
    group_stats: GroupSessionStats | None = None


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
        group_stats=(
            _group_stats(sessions)
            if conversation_type == "group"
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
    initiator, initiator_sender_key, initiator_is_self = _initiator(
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
        initiator_is_self=initiator_is_self,
    )


def _initiator(
    message: ChatMessage,
    *,
    conversation_type: str,
) -> tuple[str, str | None, bool | None]:
    sender_key = stable_sender_key(message)
    if conversation_type == "private":
        if message.is_self is True:
            return "self", sender_key, True
        if message.is_self is False:
            return "peer", sender_key, False
        return "unknown", sender_key, None
    if conversation_type == "group":
        return sender_key, sender_key, message.is_self
    return "unknown", sender_key, None


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


def _group_stats(
    sessions: tuple[ConversationSession, ...],
) -> GroupSessionStats:
    initiator_counts: dict[str, int] = {}
    for session in sessions:
        sender_key = session.initiator_sender_key
        if sender_key:
            initiator_counts[sender_key] = initiator_counts.get(sender_key, 0) + 1

    top_sender_key = max(
        initiator_counts,
        key=initiator_counts.get,
        default=None,
    )
    top_count = initiator_counts.get(top_sender_key, 0) if top_sender_key else 0
    session_count = len(sessions)
    identity_is_reliable = bool(sessions) and all(
        session.initiator_is_self is not None for session in sessions
    )
    self_count = (
        sum(session.initiator_is_self is True for session in sessions)
        if identity_is_reliable
        else None
    )
    return GroupSessionStats(
        self_initiated_count=self_count,
        self_initiated_share=(
            self_count / session_count
            if self_count is not None and session_count
            else None
        ),
        top_initiator_sender_key=top_sender_key,
        top_initiated_count=top_count,
        top_initiated_share=(top_count / session_count if session_count else 0.0),
    )
