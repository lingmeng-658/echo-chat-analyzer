"""Source-neutral conversation session segmentation and statistics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from ..message import ChatMessage
from .identity import stable_sender_key
from .timestamps import to_chat_datetime, to_epoch_seconds


DEFAULT_SESSION_THRESHOLD_SECONDS = 30 * 60

# Session character keys (deterministic, rule-based classification)
SESSION_CHARACTER_QUICK_BRIEF = "quick_and_brief"
SESSION_CHARACTER_LONG_RUNNING = "long_running"
SESSION_CHARACTER_MIXED = "mixed"

# Character boundary thresholds
_QUICK_BRIEF_MAX_MEDIAN_SECONDS = 300       # 5 minutes
_QUICK_BRIEF_MIN_SHORT_SESSION_RATIO = 0.6  # 60%
_QUICK_BRIEF_SHORT_SESSION_MAX_MESSAGES = 5
_LONG_RUNNING_MIN_MEDIAN_SECONDS = 1800     # 30 minutes
_MIN_SESSIONS_FOR_CHARACTER = 3

# Loudest densest eligibility
_DENSEST_MIN_DURATION_SECONDS = 120
_DENSEST_MIN_MESSAGE_COUNT = 10


@dataclass(frozen=True, slots=True)
class ConversationSession:
    """One continuous run of chat messages."""

    start_timestamp: int | None
    end_timestamp: int | None
    duration_seconds: int
    message_count: int
    participant_count: int
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
class HourlyActivity:
    """Message count for one hour of the day."""

    hour: int
    count: int


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
    # Group-only: start-hour distribution
    start_hour_counts: tuple[HourlyActivity, ...] = ()
    peak_start_hour: int | None = None
    # Group-only: session character (deterministic key)
    session_character: str | None = None
    # Group-only: loudest session indices (into self.sessions)
    loudest_most_messages: int | None = None
    loudest_longest_duration: int | None = None
    loudest_most_participants: int | None = None
    loudest_densest: int | None = None


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
    is_group = conversation_type == "group"

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
            _private_stats(sessions) if conversation_type == "private" else None
        ),
        group_stats=(_group_stats(sessions) if is_group else None),
        start_hour_counts=(
            _session_start_hour_analysis(sessions).start_hour_counts
            if is_group
            else ()
        ),
        peak_start_hour=(
            _session_start_hour_analysis(sessions).peak_start_hour
            if is_group
            else None
        ),
        session_character=(
            _session_character(sessions) if is_group else None
        ),
        loudest_most_messages=(
            _loudest_most_messages(sessions) if is_group else None
        ),
        loudest_longest_duration=(
            _loudest_longest_duration(sessions) if is_group else None
        ),
        loudest_most_participants=(
            _loudest_most_participants(sessions) if is_group else None
        ),
        loudest_densest=(
            _loudest_densest(sessions) if is_group else None
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
    # Count unique participants using stable sender identity
    participant_keys: set[str] = set()
    for message in messages:
        key = stable_sender_key(message)
        participant_keys.add(key)
    return ConversationSession(
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        duration_seconds=(
            end_timestamp - start_timestamp
            if start_timestamp is not None and end_timestamp is not None
            else 0
        ),
        message_count=len(messages),
        participant_count=len(participant_keys),
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


def _session_start_hour_analysis(
    sessions: tuple[ConversationSession, ...],
) -> HourlyActivity:
    """Count session start hours for the 24-hour window.

    Only sessions with a valid start_timestamp contribute.
    """
    hour_counts: dict[int, int] = {}
    for session in sessions:
        if session.start_timestamp is None:
            continue
        dt = to_chat_datetime(session.start_timestamp)
        if dt is None:
            continue
        hour = dt.hour
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

    if not hour_counts:
        return HourlyActivity(hour=0, count=0)

    counts = tuple(
        HourlyActivity(hour=h, count=hour_counts.get(h, 0))
        for h in range(24)
    )
    return HourlyActivity(hour=0, count=0)  # placeholder

@dataclass(frozen=True, slots=True)
class _StartHourResult:
    start_hour_counts: tuple[HourlyActivity, ...]
    peak_start_hour: int | None


def _session_start_hour_analysis(
    sessions: tuple[ConversationSession, ...],
) -> _StartHourResult:
    """Count session start hours for the 24-hour window.

    Only sessions with a valid start_timestamp contribute.
    """
    hour_counts: dict[int, int] = {}
    for session in sessions:
        if session.start_timestamp is None:
            continue
        dt = to_chat_datetime(session.start_timestamp)
        if dt is None:
            continue
        hour = dt.hour
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

    if not hour_counts:
        return _StartHourResult(start_hour_counts=(), peak_start_hour=None)

    counts = tuple(
        HourlyActivity(hour=h, count=hour_counts.get(h, 0))
        for h in range(24)
    )

    # Find peak with tie-break: lower hour wins
    max_count = max(hour_counts.values())
    candidates = [h for h, c in hour_counts.items() if c == max_count]
    candidates.sort()
    peak = candidates[0]

    return _StartHourResult(start_hour_counts=counts, peak_start_hour=peak)


def _session_character(
    sessions: tuple[ConversationSession, ...],
) -> str | None:
    """Determine group session character using deterministic rules.

    Returns one of the SESSION_CHARACTER_* constants, or None when there
    are too few sessions for a reliable classification.
    """
    session_count = len(sessions)
    if session_count < _MIN_SESSIONS_FOR_CHARACTER:
        return None

    median_duration = float(median([s.duration_seconds for s in sessions]))

    # quick_and_brief: short median, >60% sessions have <=5 messages
    if median_duration < _QUICK_BRIEF_MAX_MEDIAN_SECONDS:
        short_sessions = sum(
            1 for s in sessions if s.message_count <= _QUICK_BRIEF_SHORT_SESSION_MAX_MESSAGES
        )
        if short_sessions / session_count > _QUICK_BRIEF_MIN_SHORT_SESSION_RATIO:
            return SESSION_CHARACTER_QUICK_BRIEF

    # long_running: median duration > 30 minutes
    if median_duration > _LONG_RUNNING_MIN_MEDIAN_SECONDS:
        return SESSION_CHARACTER_LONG_RUNNING

    return SESSION_CHARACTER_MIXED


def _loudest_most_messages(
    sessions: tuple[ConversationSession, ...],
) -> int | None:
    """Return index of session with highest message_count.

    Tie-break: duration_seconds DESC, then start_timestamp ASC, then index ASC.
    """
    if not sessions:
        return None
    candidates = list(enumerate(sessions))
    candidates.sort(
        key=lambda item: (
            -item[1].message_count,
            -item[1].duration_seconds,
            item[1].start_timestamp or 0,
            item[0],
        ),
    )
    return candidates[0][0]


def _loudest_longest_duration(
    sessions: tuple[ConversationSession, ...],
) -> int | None:
    """Return index of session with greatest duration_seconds.

    Tie-break: message_count DESC, then start_timestamp ASC, then index ASC.
    """
    if not sessions:
        return None
    candidates = list(enumerate(sessions))
    candidates.sort(
        key=lambda item: (
            -item[1].duration_seconds,
            -item[1].message_count,
            item[1].start_timestamp or 0,
            item[0],
        ),
    )
    return candidates[0][0]


def _loudest_most_participants(
    sessions: tuple[ConversationSession, ...],
) -> int | None:
    """Return index of session with highest participant_count.

    Tie-break: message_count DESC, then start_timestamp ASC, then index ASC.
    """
    if not sessions:
        return None
    candidates = list(enumerate(sessions))
    candidates.sort(
        key=lambda item: (
            -item[1].participant_count,
            -item[1].message_count,
            item[1].start_timestamp or 0,
            item[0],
        ),
    )
    return candidates[0][0]


def _loudest_densest(
    sessions: tuple[ConversationSession, ...],
) -> int | None:
    """Return index of session with highest message density.

    Only sessions meeting minimum duration (>=120s) and message_count (>=10)
    are eligible. Density is message_count / duration_seconds.

    Avoid float equality issues by comparing cross-multiplication:
    a/b > c/d  →  a*d > c*b

    Tie-break: message_count DESC, then start_timestamp ASC, then index ASC.
    """
    eligible: list[tuple[int, ConversationSession]] = [
        (i, s)
        for i, s in enumerate(sessions)
        if s.duration_seconds >= _DENSEST_MIN_DURATION_SECONDS
        and s.message_count >= _DENSEST_MIN_MESSAGE_COUNT
    ]
    if not eligible:
        return None

    # Sort by density using cross-multiplication to avoid float precision
    def _density_key(item: tuple[int, ConversationSession]) -> tuple:
        idx, session = item
        # Density = message_count / duration_seconds; for sorting we use
        # cross-multiplication: sort by (msg_count, duration) pairs
        # Higher density means larger msg_count/duration ratio
        # We sort by -msg_count * other_duration which is equivalent
        # For tie-breaking: higher msg_count wins, then earlier start, then index
        return (
            # Primary: we cannot use a simple cross-multiplication as sort key
            # because it depends on pairwise comparison. Instead, use float
            # with a tie-break guard.
            -(session.message_count / session.duration_seconds),
            -session.message_count,
            session.start_timestamp or 0,
            idx,
        )

    eligible.sort(key=_density_key)
    # Verify the top result is not a float equality artifact by re-checking
    if len(eligible) >= 2:
        top = eligible[0][1]
        second = eligible[1][1]
        top_density = top.message_count * second.duration_seconds
        second_density = second.message_count * top.duration_seconds
        if top_density == second_density:
            # True tie: resolve by message_count DESC, then start_timestamp, then index
            tied = [eligible[0], eligible[1]]
            tied.sort(
                key=lambda item: (
                    -item[1].message_count,
                    -item[1].duration_seconds,
                    item[1].start_timestamp or 0,
                    item[0],
                ),
            )
            if tied[0] is not eligible[0]:
                eligible[0] = tied[0]
                # Re-sort rest
                eligible.sort(key=_density_key)

    return eligible[0][0]
