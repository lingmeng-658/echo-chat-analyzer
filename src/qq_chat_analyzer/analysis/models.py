"""Source-neutral report models for extended chat analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from .conversation_sessions import ConversationSessionReport


UNKNOWN_CONVERSATION_NAME = "\u672a\u77e5\u4f1a\u8bdd"

INTERNAL_ID_SUFFIXES = ("@chatroom",)
INTERNAL_ID_PREFIXES = ("wxid_",)


def is_displayable_conversation_id(conversation_id: str | None) -> bool:
    """Return whether a raw conversation key is safe to show to a user.

    Internal handles such as ``wxid_abc`` or ``12345@chatroom`` carry no
    meaning for readers, so they are hidden behind a generic label.
    """
    if not conversation_id:
        return False

    candidate = conversation_id.strip()
    if not candidate:
        return False

    lowered = candidate.lower()
    if lowered.startswith(INTERNAL_ID_PREFIXES):
        return False
    if lowered.endswith(INTERNAL_ID_SUFFIXES):
        return False
    return True


@dataclass(frozen=True, slots=True)
class HourlyActivity:
    """Message count for one hour of the day."""

    hour: int
    count: int


@dataclass(frozen=True, slots=True)
class WeekdayActivity:
    """Message count for one weekday, where Monday is zero."""

    weekday: int
    count: int


@dataclass(frozen=True, slots=True)
class ActivityReport:
    """Temporal distribution of messages across hours and weekdays."""

    total_message_count: int
    dated_message_count: int
    hourly_counts: tuple[HourlyActivity, ...] = ()
    weekday_counts: tuple[WeekdayActivity, ...] = ()
    busiest_hour: int | None = None
    busiest_weekday: int | None = None
    hour_distribution: Mapping[int, int] = field(default_factory=dict)
    weekday_distribution: Mapping[str, int] = field(default_factory=dict)
    peak_hour: int | None = None
    peak_weekday: str | None = None


@dataclass(frozen=True, slots=True)
class LengthBucket:
    """Message count for one half-open message-length range."""

    lower_bound: int
    upper_bound: int | None
    count: int


@dataclass(frozen=True, slots=True)
class SpeakerLength:
    """Message length statistics for one speaker."""

    speaker: str
    message_count: int
    average_length: float
    max_length: int


@dataclass(frozen=True, slots=True)
class MessageLengthReport:
    """Global and per-speaker message length statistics."""

    message_count: int
    average_length: float
    max_length: int
    buckets: tuple[LengthBucket, ...] = ()
    speaker_lengths: tuple[SpeakerLength, ...] = ()


@dataclass(frozen=True, slots=True)
class ProfileWord:
    """One frequent word attributed to a single speaker."""

    word: str
    count: int


@dataclass(frozen=True, slots=True)
class UserProfile:
    """Combined activity and length profile for one speaker."""

    speaker: str
    message_count: int
    message_share_percent: float
    average_length: float
    max_length: int
    busiest_hour: int | None = None
    busiest_weekday: int | None = None
    top_words: tuple[ProfileWord, ...] = ()
    display_name: str | None = None
    hourly_counts: tuple[HourlyActivity, ...] = ()
    weekday_counts: tuple[WeekdayActivity, ...] = ()
    speaker_key: str | None = None
    remark: str | None = None
    nickname: str | None = None
    contextual_name: str | None = None

    @property
    def resolved_display_name(self) -> str:
        """Return the friendly name, falling back to the raw speaker key."""
        return self.display_name or self.speaker


@dataclass(frozen=True, slots=True)
class UserProfileReport:
    """Per-speaker profiles ordered by message volume."""

    total_message_count: int
    speaker_count: int = 0
    profiles: tuple[UserProfile, ...] = ()


class DistinctiveWordAvailability(str, Enum):
    """Why a distinctive-word report is or is not displayable."""

    AVAILABLE = "available"
    NOT_GROUP = "not_group"
    INSUFFICIENT_MEMBERS = "insufficient_members"


@dataclass(frozen=True, slots=True)
class DistinctiveWord:
    """One member word ranked by smoothed log-odds z-score."""

    word: str
    count: int
    member_rate: float
    others_rate: float
    relative_ratio: float
    ranking_score: float


@dataclass(frozen=True, slots=True)
class MemberDistinctiveWords:
    """Distinctive words for one member who passed sample thresholds."""

    speaker_key: str
    tokenized_message_count: int
    token_count: int
    eligible_word_candidate_count: int
    words: tuple[DistinctiveWord, ...] = ()


@dataclass(frozen=True, slots=True)
class DistinctiveWordReport:
    """Source-neutral group distinctive-word analysis result."""

    conversation_type: str
    availability: DistinctiveWordAvailability
    eligible_member_count: int = 0
    members: tuple[MemberDistinctiveWords, ...] = ()

    @property
    def available(self) -> bool:
        return self.availability is DistinctiveWordAvailability.AVAILABLE


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    """Volume, span, and participation for one conversation."""

    conversation_id: str | None
    message_count: int
    speaker_count: int
    start_timestamp: int | None = None
    end_timestamp: int | None = None
    duration_seconds: int | None = None
    display_name: str | None = None

    @property
    def resolved_display_name(self) -> str:
        """Return the friendly name, hiding internal conversation keys.

        Falls back to `conversation_id` when it is human-readable, and to
        `UNKNOWN_CONVERSATION_NAME` when the key is an internal handle.
        """
        if self.display_name and self.display_name.strip():
            return self.display_name.strip()
        if is_displayable_conversation_id(self.conversation_id):
            return self.conversation_id.strip()
        return UNKNOWN_CONVERSATION_NAME


@dataclass(frozen=True, slots=True)
class ConversationReport:
    """Aggregate view of every conversation in one analysis run."""

    conversation_count: int
    conversations: tuple[ConversationSummary, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisReports:
    """Bundle of every extended report produced for one analysis run."""

    activity: ActivityReport | None = None
    message_length: MessageLengthReport | None = None
    user_profiles: UserProfileReport | None = None
    conversations: ConversationReport | None = None
    message_composition: MessageCompositionReport | None = None
    conversation_sessions: ConversationSessionReport | None = None
    distinctive_words: DistinctiveWordReport | None = None


@dataclass(frozen=True, slots=True)
class MessageCompositionCategory:
    """Message count for one display category."""

    category: str
    count: int


@dataclass(frozen=True, slots=True)
class MessageCompositionReport:
    """Message counts grouped by display category, excluding system messages."""

    total_count: int
    categories: tuple[MessageCompositionCategory, ...] = ()
