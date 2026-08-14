"""Framework-neutral view models for presenting analysis reports.

These models intentionally expose only display-ready primitives so a future
GUI never has to reach into the analysis report structures. Nothing here
computes statistics: every number is copied from an already-built report.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ChartKind(str, Enum):
    """Supported chart shapes a view layer may render."""

    BAR = "bar"
    LINE = "line"
    HEATMAP = "heatmap"
    RANKING = "ranking"


@dataclass(frozen=True, slots=True)
class MetricCard:
    """One headline number with a human readable label."""

    key: str
    title: str
    value: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class ChartPoint:
    """One plottable value with its display label."""

    label: str
    value: float


@dataclass(frozen=True, slots=True)
class ChartSeries:
    """A named sequence of points belonging to one chart."""

    name: str
    points: tuple[ChartPoint, ...] = ()


@dataclass(frozen=True, slots=True)
class ChartData:
    """Display-ready chart description for any supported chart kind."""

    key: str
    kind: ChartKind
    title: str
    series: tuple[ChartSeries, ...] = ()
    x_axis_label: str = ""
    y_axis_label: str = ""
    description: str = ""

    @property
    def is_empty(self) -> bool:
        """Report whether the chart has any point to draw."""
        return all(not series.points for series in self.series)


@dataclass(frozen=True, slots=True)
class UserCard:
    """Display-ready profile for one speaker."""

    rank: int
    sender: str
    message_count: int
    percentage: float
    average_length: float
    percentage_display: str
    average_length_display: str
    active_period: str
    top_words: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConversationCard:
    """Display-ready summary for one conversation."""

    conversation_id: str
    message_count: int
    participant_count: int
    time_span: str


@dataclass(frozen=True, slots=True)
class DashboardView:
    """Complete, GUI-agnostic payload for one analysis dashboard."""

    title: str
    has_data: bool = False
    summary_metrics: tuple[MetricCard, ...] = ()
    charts: tuple[ChartData, ...] = ()
    user_cards: tuple[UserCard, ...] = ()
    conversation_cards: tuple[ConversationCard, ...] = ()
    empty_description: str = ""


@dataclass(frozen=True, slots=True)
class EchoMemberCard:
    """Display-ready Echo profile for one conversation member."""

    speaker_key: str
    display_name: str
    is_viewer: bool
    message_count: int
    message_share_percent: float
    average_length: float
    max_length: int
    active_period: str
    hourly_activity: tuple[ChartPoint, ...] = ()
    weekday_activity: tuple[ChartPoint, ...] = ()
    top_words: tuple[str, ...] = ()
    primary_name: str | None = None
    secondary_name: str | None = None
    remark: str | None = None
    contextual_name: str | None = None


@dataclass(frozen=True, slots=True)
class EchoLanguageMember:
    """One display-ready voice in Echo's language-profile chapter."""

    speaker_key: str
    display_name: str
    heading: str
    primary_words: tuple[str, ...] = ()
    context_words: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EchoLanguageProfile:
    """Prepared group/private product branch for the Echo frontend."""

    mode: str
    available: bool
    members: tuple[EchoLanguageMember, ...] = ()
    unavailable_reason: str = ""


@dataclass(frozen=True, slots=True)
class EchoConversationSession:
    """Display-neutral session detail carried to Echo serialization."""

    start_timestamp: int | None
    end_timestamp: int | None
    duration_seconds: int
    message_count: int
    initiator: str
    participant_count: int = 1
    initiator_sender_key: str | None = None
    self_message_count: int | None = None
    peer_message_count: int | None = None


@dataclass(frozen=True, slots=True)
class EchoConversationSessions:
    """Session aggregate payload prepared for Echo."""

    threshold_seconds: int
    session_count: int
    average_duration_seconds: float
    median_duration_seconds: float
    longest_duration_seconds: int
    average_message_count: float
    items: tuple[EchoConversationSession, ...] = ()
    private_self_count: int | None = None
    private_peer_count: int | None = None
    private_unknown_count: int | None = None
    private_self_to_peer_ratio: float | None = None
    private_self_share: float | None = None
    private_peer_share: float | None = None
    private_unknown_share: float | None = None
    private_self_peak_start_hour: int | None = None
    private_peer_peak_start_hour: int | None = None
    private_reply_median_self_to_peer_seconds: float | None = None
    private_reply_median_peer_to_self_seconds: float | None = None
    group_self_count: int | None = None
    group_self_share: float | None = None
    group_top_initiator_name: str | None = None
    group_top_initiator_count: int | None = None
    group_top_initiator_share: float | None = None
    viewer_identity_reliable: bool = False
    start_hour_distribution: tuple[ChartPoint, ...] = ()
    peak_start_hour: int | None = None
    session_character: str | None = None
    loudest_most_messages: EchoConversationSession | None = None
    loudest_longest_duration: EchoConversationSession | None = None
    loudest_most_participants: EchoConversationSession | None = None
    loudest_densest: EchoConversationSession | None = None
    loudest_most_back_and_forth: EchoConversationSession | None = None


@dataclass(frozen=True, slots=True)
class EchoReportView:
    """Display-only payload for Echo Report v0.1 Phase A."""

    title: str
    has_data: bool = False
    conversation_kind: str = "unknown"
    conversation_name: str = ""
    time_span: str = ""
    total_message_count: int = 0
    participant_count: int = 0
    hourly_activity: tuple[ChartPoint, ...] = ()
    weekday_activity: tuple[ChartPoint, ...] = ()
    members: tuple[EchoMemberCard, ...] = ()
    conversation_sessions: EchoConversationSessions | None = None
    language_profile: EchoLanguageProfile | None = None
    empty_description: str = ""
