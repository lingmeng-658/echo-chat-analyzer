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